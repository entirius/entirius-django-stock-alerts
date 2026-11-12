# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
import threading

import pytest
from django.db import connection

from django_stock_alerts import settings as stock_settings
from django_stock_alerts.enums import CancelReason, Status
from django_stock_alerts.models import Subscription
from django_stock_alerts.services import subscription_service as service
from tests.conftest import CHANNEL_IDX, EMAIL, PARENT_SKU, SKU, SKU_2, subscribe_data

pytestmark = pytest.mark.django_db


def test_new_request_keeps_consent_and_parent(products, quantities):
    row, created = service.subscribe(subscribe_data())
    assert created
    assert (row.status, row.email, row.parent_sku, row.country) == (Status.WAITING, EMAIL, PARENT_SKU, "pl")
    assert row.consent_text == "Email me when it is back."
    assert row.consent_at is not None


def test_same_request_returns_the_same_row(products, quantities):
    first, _ = service.subscribe(subscribe_data())
    again, created = service.subscribe(subscribe_data(email="  Anna@Example.COM "))
    assert (again.pk, created) == (first.pk, False)
    assert Subscription.objects.count() == 1


def test_second_sku_is_a_second_row(products, quantities):
    service.subscribe(subscribe_data())
    service.subscribe(subscribe_data(sku=SKU_2))
    assert Subscription.objects.count() == 2


def test_sku_in_stock_is_refused(products, quantities):
    quantities[SKU] = 3
    with pytest.raises(service.InStock):
        service.subscribe(subscribe_data())


@pytest.mark.parametrize("sku", ["NOPE", PARENT_SKU])
def test_unknown_sku_or_parent_is_refused(products, quantities, sku):
    with pytest.raises(service.ProductNotFound):
        service.subscribe(subscribe_data(sku=sku))


def test_channel_without_templates_is_closed(products, quantities, monkeypatch):
    monkeypatch.setattr(stock_settings, "PRODUCT_URL", {})
    with pytest.raises(service.ChannelClosed):
        service.subscribe(subscribe_data())


def test_cap_per_address(products, quantities, monkeypatch):
    monkeypatch.setattr(stock_settings, "MAX_WAITING_PER_EMAIL", 1)
    service.subscribe(subscribe_data())
    with pytest.raises(service.TooManyRequests):
        service.subscribe(subscribe_data(sku=SKU_2))
    assert service.subscribe(subscribe_data())[1] is False  # the existing request is no new one


@pytest.mark.parametrize("closed", [Status.NOTIFIED, Status.CANCELLED])
def test_resubscribe_after_a_closed_request(products, quantities, closed):
    first, _ = service.subscribe(subscribe_data())
    Subscription.objects.filter(pk=first.pk).update(status=closed)
    second, created = service.subscribe(subscribe_data())
    assert created and second.pk != first.pk


def test_cancel_is_idempotent(products, quantities):
    row, _ = service.subscribe(subscribe_data())
    service.cancel(row, CancelReason.ADMIN)
    cancelled_at = row.cancelled_at
    service.cancel(row, CancelReason.USER)
    row.refresh_from_db()
    assert (row.status, row.cancel_reason, row.cancelled_at) == (Status.CANCELLED, CancelReason.ADMIN, cancelled_at)


@pytest.mark.django_db(transaction=True)
def test_race_two_subscribes_one_row(products, quantities, monkeypatch):
    """Both requests pass the lookup before either inserts: the unique index decides, the loser re-reads."""
    barrier, results = threading.Barrier(2, timeout=10), []
    monkeypatch.setattr(service, "_check_cap", lambda *args: barrier.wait())

    def run():
        try:
            results.append(service.subscribe(subscribe_data()))
        finally:
            connection.close()

    threads = [threading.Thread(target=run) for _ in range(2)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    assert len(results) == 2
    assert len({row.pk for row, _ in results}) == 1
    assert Subscription.objects.filter(channel_idx=CHANNEL_IDX, sku=SKU).count() == 1
