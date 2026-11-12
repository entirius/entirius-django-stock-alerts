# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
import pytest

from django_stock_alerts.enums import CancelReason, Status
from django_stock_alerts.gdpr import anonymised_address, gdpr_erase, gdpr_export
from django_stock_alerts.models import Subscription
from django_stock_alerts.services import subscription_service as service
from tests.conftest import EMAIL, SKU_2, WITH_AGREEMENTS, subscribe_data

pytestmark = pytest.mark.django_db


def test_export_by_plain_address(products, quantities):
    row, _ = service.subscribe(subscribe_data())
    [exported] = gdpr_export(" Anna@Example.com")["Subscription"]
    assert (exported["id"], exported["email"]) == (row.pk, EMAIL)


def test_erase_cancels_waiting_and_anonymises_all(products, quantities):
    waiting, _ = service.subscribe(subscribe_data())
    closed, _ = service.subscribe(subscribe_data(sku=SKU_2))
    Subscription.objects.filter(pk=closed.pk).update(status=Status.NOTIFIED)
    other, _ = service.subscribe(subscribe_data(email="other@example.com"))
    assert gdpr_erase(EMAIL) == {"subscriptions": 2}
    waiting.refresh_from_db()
    closed.refresh_from_db()
    assert (waiting.status, waiting.cancel_reason) == (Status.CANCELLED, CancelReason.ERASED)
    assert closed.status == Status.NOTIFIED
    for row in (waiting, closed):
        assert (row.email, row.anonymised_at is not None) == (anonymised_address(EMAIL), True)
    other.refresh_from_db()
    assert other.email == "other@example.com"


def test_export_by_token_after_erasure(products, quantities):
    service.subscribe(subscribe_data())
    gdpr_erase(EMAIL)
    [exported] = gdpr_export(EMAIL)["Subscription"]
    assert exported["email"] == anonymised_address(EMAIL)


@pytest.mark.skipif(not WITH_AGREEMENTS, reason="django_agreements is not installed")
def test_erase_writes_the_withdrawal_under_the_token(agreement, products, quantities):
    from django_agreements.models import ConsentRecord

    service.subscribe(subscribe_data())
    gdpr_erase(EMAIL)
    withdrawal = ConsentRecord.objects.get(granted=False)
    assert withdrawal.email == anonymised_address(EMAIL)


def test_token_parity_with_leads():
    emails = pytest.importorskip("django_leads.utils.emails")
    for email in (EMAIL, " Mixed.Case@Example.COM ", ""):
        assert anonymised_address(email) == emails.anonymised_address(email)
