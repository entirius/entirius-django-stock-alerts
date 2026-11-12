# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
from datetime import timedelta
from itertools import count
from unittest.mock import patch

import pytest
from django.core.cache import cache
from django.db import connection
from django.test.utils import CaptureQueriesContext
from django.utils import timezone

from django_stock_alerts import settings as stock_settings
from django_stock_alerts.models import Subscription
from django_stock_alerts.services import check_service
from django_stock_alerts.tasks.check import LOCK_KEY, check

from .conftest import CHANNEL_IDX, SKU, SKU_2, make_row


@pytest.fixture
def enqueued():
    """`send_alert.delay` of the check task, recorded instead of sent to a broker."""
    with patch("django_stock_alerts.tasks.send.send_alert.delay") as delay:
        yield delay


_people = count()


def waiting(rows: int, sku: str = SKU) -> list[int]:
    """`rows` waiting rows of new addresses, oldest first (one minute apart)."""
    now = timezone.now()
    pks = []
    for i in range(rows):
        row = make_row(sku=sku, email=f"person{next(_people)}@example.com")
        Subscription.objects.filter(pk=row.pk).update(created_at=now - timedelta(minutes=rows - i))
        pks.append(row.pk)
    return pks


def enqueued_pks(delay) -> list[int]:
    return [c.args[0] for c in delay.call_args_list]


def test_no_waiting_rows_reads_no_quantity(db, enqueued):
    with patch("django_stock_alerts.services.catalog.get_quantities") as get_quantities:
        assert check() == 0

    get_quantities.assert_not_called()
    enqueued.assert_not_called()


def test_sold_out_enqueues_nothing(products, quantities, enqueued):
    waiting(3)

    assert check() == 0
    enqueued.assert_not_called()


def test_wave_is_quantity_times_factor_oldest_first_and_the_next_skips_claimed(products, quantities, enqueued):
    pks = waiting(30)
    quantities[SKU] = 2

    assert check() == 10
    assert enqueued_pks(enqueued) == pks[:10]
    enqueued.reset_mock()

    assert check() == 10
    assert enqueued_pks(enqueued) == pks[10:20]


def test_a_stale_claim_is_taken_again(products, quantities, enqueued):
    pks = waiting(2)
    quantities[SKU] = 1
    Subscription.objects.update(wave_claimed_at=timezone.now() - check_service.CLAIM_TTL - timedelta(seconds=1))

    check()

    assert enqueued_pks(enqueued) == pks


def test_factor_zero_takes_everyone(products, quantities, enqueued, monkeypatch):
    monkeypatch.setattr(stock_settings, "WAVE_FACTOR", 0)
    pks = waiting(12)
    quantities[SKU] = 1

    assert check() == 12
    assert enqueued_pks(enqueued) == pks


def test_channel_without_templates_is_skipped(products, quantities, enqueued, monkeypatch):
    monkeypatch.delitem(stock_settings.CANCEL_URL, CHANNEL_IDX)
    waiting(2)
    quantities[SKU] = 5

    assert check() == 0


def test_batches_of_skus(products, quantities, enqueued, monkeypatch):
    monkeypatch.setattr(stock_settings, "CHECK_BATCH", 1)
    waiting(1, SKU)
    waiting(1, SKU_2)
    quantities.update({SKU: 1, SKU_2: 1})

    result = check_service.run_check(enqueued)

    assert (result.skus, result.back, result.enqueued) == (2, 2, 2)


def test_overlapping_run_is_blocked_by_the_lock(products, quantities, enqueued):
    waiting(2)
    quantities[SKU] = 1
    cache.add(LOCK_KEY, 1, 60)

    assert check() is None
    enqueued.assert_not_called()

    cache.delete(LOCK_KEY)
    assert check() == 2


def test_the_lock_is_released_after_a_failed_run(products, quantities, enqueued):
    waiting(1)
    quantities[SKU] = 1
    enqueued.side_effect = ConnectionError

    with pytest.raises(ConnectionError):
        check()

    assert cache.get(LOCK_KEY) is None


def test_log_line(products, quantities, enqueued, caplog):
    waiting(2)
    quantities[SKU] = 1

    with caplog.at_level("INFO", logger="django_stock_alerts.tasks.check"):
        check()

    assert f"event=stock_alerts.check channels={CHANNEL_IDX} skus=1 back=1 enqueued=2" in caplog.text


def _queries_of_one_run() -> int:
    Subscription.objects.update(wave_claimed_at=None)
    with CaptureQueriesContext(connection) as ctx:
        check_service.run_check(lambda pk: None)
    return len(ctx.captured_queries)


def test_queries_do_not_grow_with_subscribers(products, quantities, monkeypatch):
    monkeypatch.setattr(stock_settings, "WAVE_FACTOR", 0)
    quantities[SKU] = 1
    waiting(2)
    few = _queries_of_one_run()
    waiting(40)

    assert _queries_of_one_run() == few <= 4
