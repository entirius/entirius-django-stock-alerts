# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""The consent's second record in django_agreements (soft dependency)."""

import pytest

from django_stock_alerts import settings as stock_settings
from django_stock_alerts.enums import CancelReason
from django_stock_alerts.services import consent_bridge
from django_stock_alerts.services import subscription_service as service
from tests.conftest import EMAIL, WITH_AGREEMENTS, subscribe_data

pytestmark = pytest.mark.django_db
needs_agreements = pytest.mark.skipif(not WITH_AGREEMENTS, reason="django_agreements is not installed")


def _records():
    from django_agreements.models import ConsentRecord

    return ConsentRecord.objects.filter(agreement_version__definition__slug="stock-alerts").order_by("pk")


@needs_agreements
def test_new_request_writes_one_grant(agreement, products, quantities):
    row, _ = service.subscribe(subscribe_data())
    service.subscribe(subscribe_data())  # a repeated request writes none
    [record] = _records()
    assert row.consent_record_id == record.pk
    assert (record.email, record.granted, record.source, record.channel_idx) == (
        EMAIL,
        True,
        "stock_alerts",
        row.channel_idx,
    )
    assert (record.ip_address, record.user_agent) == ("203.0.113.7", "pytest-agent")


@needs_agreements
@pytest.mark.parametrize("reason", [CancelReason.USER, CancelReason.ERASED])
def test_cancel_by_the_person_writes_a_withdrawal(agreement, products, quantities, reason):
    row, _ = service.subscribe(subscribe_data())
    service.cancel(row, reason)
    assert [record.granted for record in _records()] == [True, False]


@needs_agreements
@pytest.mark.parametrize("reason", [CancelReason.ADMIN, CancelReason.UNDELIVERABLE])
def test_cancel_by_others_writes_none(agreement, products, quantities, reason):
    row, _ = service.subscribe(subscribe_data())
    service.cancel(row, reason)
    assert [record.granted for record in _records()] == [True]


@needs_agreements
def test_never_a_marketing_subscriber(agreement, products, quantities):
    from django_agreements.services.consent_service import list_active_marketing_subscribers

    service.subscribe(subscribe_data())
    assert not list_active_marketing_subscribers().filter(email=EMAIL).exists()


@needs_agreements
@pytest.mark.parametrize("state", ["missing", "unpublished"])
def test_missing_definition_saves_the_request(products, quantities, state):
    from django_agreements.models import AgreementDefinition, AgreementVersion

    if state == "unpublished":
        definition = AgreementDefinition.objects.create(slug="stock-alerts", name="x", category="informational")
        AgreementVersion.objects.create(definition=definition, version_number=1)
    row, created = service.subscribe(subscribe_data())
    assert created and row.consent_record_id is None


def test_slug_none_writes_nothing(products, quantities, monkeypatch, agreement_if_installed):
    monkeypatch.setattr(stock_settings, "AGREEMENT_SLUG", None)
    row, _ = service.subscribe(subscribe_data())
    assert row.consent_record_id is None
    assert consent_bridge.record_grant(row, None, "") is None


@pytest.mark.skipif(WITH_AGREEMENTS, reason="runs without django_agreements")
def test_without_the_app(products, quantities):
    row, created = service.subscribe(subscribe_data())
    assert created and row.consent_record_id is None
    service.cancel(row, CancelReason.USER)
