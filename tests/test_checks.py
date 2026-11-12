# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
import pytest

from django_stock_alerts import checks
from django_stock_alerts import settings as stock_settings
from django_stock_alerts.services import subscription_service as service
from tests.conftest import WITH_AGREEMENTS, subscribe_data

pytestmark = pytest.mark.django_db


def _ids(messages) -> list[str]:
    return [message.id for message in messages]


def test_complete_templates_pass():
    assert checks.templates_complete() == []


def test_template_without_its_placeholder_errors(monkeypatch):
    monkeypatch.setattr(stock_settings, "PRODUCT_URL", {"default-europe": "https://shop.example/product"})
    monkeypatch.setattr(stock_settings, "CANCEL_URL", {"default-europe": "https://shop.example/cancel"})
    assert _ids(checks.templates_complete()) == [checks.BAD_TEMPLATE, checks.BAD_TEMPLATE]


def test_waiting_channel_without_templates_warns(products, quantities, monkeypatch):
    service.subscribe(subscribe_data())
    assert checks.waiting_channels_configured() == []
    monkeypatch.setattr(stock_settings, "CANCEL_URL", {})
    assert _ids(checks.waiting_channels_configured()) == [checks.NO_TEMPLATES]


@pytest.mark.skipif(not WITH_AGREEMENTS, reason="django_agreements is not installed")
def test_unpublished_agreement_warns(monkeypatch):
    assert _ids(checks.agreement_published()) == [checks.NO_AGREEMENT]
    monkeypatch.setattr(stock_settings, "AGREEMENT_SLUG", None)
    assert checks.agreement_published() == []


@pytest.mark.skipif(not WITH_AGREEMENTS, reason="django_agreements is not installed")
def test_published_agreement_passes(agreement):
    assert checks.agreement_published() == []
