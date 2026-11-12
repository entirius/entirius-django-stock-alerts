# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
import threading
import time
from datetime import timedelta
from smtplib import SMTPException
from unittest.mock import patch

import pytest
from django.db import connection
from django.utils import timezone
from django_email.service.stock_alerts.available import StockAlertAvailableEmail

from django_stock_alerts.enums import CancelReason, Status
from django_stock_alerts.tasks.check import check
from django_stock_alerts.tasks.send import RETRY_COUNTDOWNS, send_alert

from .conftest import SKU, make_row

SMTP_SEND = "django.core.mail.backends.locmem.EmailBackend.send_messages"


@pytest.fixture
def claimed(products, mailbox):
    return make_row(wave_claimed_at=timezone.now())


def run(pk: int) -> str:
    """The task with Celery's eager retries (countdowns skipped)."""
    return send_alert.apply(args=[pk]).get()


def test_waiting_and_in_stock_sends_one_alert(claimed, quantities, mailbox):
    quantities[SKU] = 1

    assert run(claimed.pk) == "notified"

    claimed.refresh_from_db()
    assert (claimed.status, claimed.wave_claimed_at) == (Status.NOTIFIED, None)
    assert claimed.notified_at is not None
    assert len(mailbox) == 1
    assert mailbox[0].to == [claimed.email]
    assert f"variant={SKU}" in mailbox[0].body
    assert mailbox[0].extra_headers["List-Unsubscribe"].startswith("<https://shop.example/pl/stock-alert/cancel?")


def test_already_notified_sends_nothing(claimed, quantities, mailbox):
    quantities[SKU] = 1
    run(claimed.pk)

    assert run(claimed.pk) == "skipped"
    assert len(mailbox) == 1


def test_sold_out_again_clears_the_claim_and_keeps_waiting(claimed, quantities, mailbox):
    assert run(claimed.pk) == "sold_out"

    claimed.refresh_from_db()
    assert (claimed.status, claimed.wave_claimed_at) == (Status.WAITING, None)
    assert mailbox == []


def test_product_gone_is_undeliverable(claimed, quantities, mailbox):
    quantities["GONE"] = 3
    claimed.sku = "GONE"
    claimed.save()

    assert run(claimed.pk) == "undeliverable"

    claimed.refresh_from_db()
    assert (claimed.status, claimed.cancel_reason) == (Status.CANCELLED, CancelReason.UNDELIVERABLE)
    assert mailbox == []


def test_smtp_error_is_retried(claimed, quantities, mailbox):
    quantities[SKU] = 1
    real_send = StockAlertAvailableEmail.send
    calls = []

    def flaky(service, **kwargs):
        calls.append(1)
        if len(calls) == 1:
            raise SMTPException("try later")
        return real_send(service, **kwargs)

    with patch.object(StockAlertAvailableEmail, "send", flaky):
        assert run(claimed.pk) == "notified"

    assert len(calls) == 2
    assert len(mailbox) == 1


def test_retry_countdowns(claimed, quantities):
    quantities[SKU] = 1
    with patch(SMTP_SEND, side_effect=OSError("refused")), patch.object(send_alert, "retry") as retry:
        retry.side_effect = RuntimeError("retry scheduled")
        with pytest.raises(RuntimeError):
            send_alert(claimed.pk)

    assert retry.call_args.kwargs["countdown"] == RETRY_COUNTDOWNS[0]


def test_retries_exhausted_twice_close_the_request(claimed, quantities, mailbox):
    quantities[SKU] = 1
    with patch(SMTP_SEND, side_effect=SMTPException("down")) as smtp:
        assert run(claimed.pk) == "failed"
        claimed.refresh_from_db()
        assert (claimed.status, claimed.send_attempts, claimed.wave_claimed_at) == (Status.WAITING, 1, None)

        assert run(claimed.pk) == "failed"

    claimed.refresh_from_db()
    assert smtp.call_count == 2 * (len(RETRY_COUNTDOWNS) + 1)
    assert (claimed.status, claimed.cancel_reason, claimed.send_attempts) == (
        Status.CANCELLED,
        CancelReason.UNDELIVERABLE,
        2,
    )


@pytest.mark.django_db(transaction=True, serialized_rollback=True)
def test_two_concurrent_tasks_send_one_message(claimed, quantities, mailbox):
    quantities[SKU] = 1
    real_send = StockAlertAvailableEmail.send

    def slow(service, **kwargs):
        time.sleep(0.3)  # the second task reaches the row lock meanwhile
        return real_send(service, **kwargs)

    results = []

    def worker():
        try:
            results.append(send_alert(claimed.pk))
        finally:
            connection.close()

    with patch.object(StockAlertAvailableEmail, "send", slow):
        threads = [threading.Thread(target=worker) for _ in range(2)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()

    assert sorted(results) == ["notified", "skipped"]
    assert len(mailbox) == 1


def test_a_scheduled_retry_keeps_the_row_out_of_the_next_waves(claimed, quantities):
    quantities[SKU] = 1
    with patch(SMTP_SEND, side_effect=OSError("refused")), patch.object(send_alert, "retry") as retry:
        retry.side_effect = RuntimeError("retry scheduled")
        with pytest.raises(RuntimeError):
            send_alert(claimed.pk)

    claimed.refresh_from_db()
    assert claimed.wave_claimed_at > timezone.now() + timedelta(seconds=RETRY_COUNTDOWNS[0] - 5)
    with patch("django_stock_alerts.tasks.send.send_alert.delay") as delay:
        check()
    delay.assert_not_called()


def test_a_configuration_error_keeps_the_request_waiting(products, quantities):
    """No django_email channel: the task fails loudly; the row waits and the next wave tries again."""
    row = make_row(wave_claimed_at=timezone.now())
    quantities[SKU] = 1

    with pytest.raises(ValueError):
        send_alert(row.pk)

    row.refresh_from_db()
    assert (row.status, row.send_attempts) == (Status.WAITING, 0)
