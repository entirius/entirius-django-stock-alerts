# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
from smtplib import SMTPException
from unittest.mock import patch

import pytest

from django_stock_alerts import settings as stock_settings
from django_stock_alerts.enums import Status
from django_stock_alerts.models import Subscription
from django_stock_alerts.tasks.send import send_signup

from .conftest import body, subscribe_url


@pytest.fixture
def delay():
    with patch("django_stock_alerts.tasks.send.send_signup.delay") as delay:
        yield delay


def test_created_request_enqueues_one_signup_email(
    api, products, quantities, mailbox, delay, django_capture_on_commit_callbacks
):
    with django_capture_on_commit_callbacks(execute=True):
        assert api.post(subscribe_url(), body(), format="json").status_code == 201
        api.post(subscribe_url(), body(), format="json")

    delay.assert_called_once_with(Subscription.objects.get().pk)


def test_setting_off_sends_none(
    api, products, quantities, mailbox, delay, monkeypatch, django_capture_on_commit_callbacks
):
    monkeypatch.setattr(stock_settings, "SIGNUP_EMAIL", False)

    with django_capture_on_commit_callbacks(execute=True):
        api.post(subscribe_url(), body(), format="json")

    delay.assert_not_called()


def test_signup_task_sends_one_message(api, products, quantities, mailbox, django_capture_on_commit_callbacks):
    with patch("django_stock_alerts.tasks.send.send_signup.delay", side_effect=lambda pk: send_signup.apply(args=[pk])):
        with django_capture_on_commit_callbacks(execute=True):
            api.post(subscribe_url(), body(), format="json")
            api.post(subscribe_url(), body(), format="json")

    assert len(mailbox) == 1
    assert mailbox[0].subject == f"We will let you know when {Subscription.objects.get().sku} is back"
    assert "List-Unsubscribe" in mailbox[0].extra_headers


def test_failed_signup_email_leaves_the_row(products, quantities, mailbox, api, django_capture_on_commit_callbacks):
    with django_capture_on_commit_callbacks(execute=False):
        api.post(subscribe_url(), body(), format="json")
    row = Subscription.objects.get()

    with patch("django.core.mail.backends.locmem.EmailBackend.send_messages", side_effect=SMTPException):
        send_signup.apply(args=[row.pk]).get()

    row.refresh_from_db()
    assert (row.status, row.send_attempts) == (Status.WAITING, 0)
    assert mailbox == []
