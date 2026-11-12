# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
import pytest
from django.core import signing

from django_stock_alerts import settings as stock_settings
from django_stock_alerts.enums import CancelReason, Status
from django_stock_alerts.gdpr import gdpr_erase
from django_stock_alerts.models import Subscription
from django_stock_alerts.services import subscription_service, token_service
from tests.conftest import EMAIL, SKU, SKU_2, WITH_AGREEMENTS, body, cancel_url, subscribe_data, subscribe_url

pytestmark = pytest.mark.django_db


def test_new_and_existing_request_answer_the_same_bytes(api, products, quantities):
    first = api.post(subscribe_url(), body(), format="json")
    second = api.post(subscribe_url(), body(email=EMAIL.upper()), format="json")
    assert first.status_code == second.status_code == 201
    assert first.content == second.content == b'{"status":"saved"}'
    assert Subscription.objects.count() == 1


def test_in_stock_is_a_conflict(api, products, quantities):
    quantities[SKU] = 1
    response = api.post(subscribe_url(), body(), format="json")
    assert (response.status_code, response.json()["error"]) == (409, "IN_STOCK")


def test_unknown_sku_is_not_found(api, products, quantities):
    assert api.post(subscribe_url(), body(sku="NOPE"), format="json").status_code == 404


def test_cap_reached(api, products, quantities, monkeypatch):
    monkeypatch.setattr(stock_settings, "MAX_WAITING_PER_EMAIL", 1)
    api.post(subscribe_url(), body(), format="json")
    response = api.post(subscribe_url(), body(sku=SKU_2), format="json")
    assert (response.status_code, response.json()["error"]) == (429, "TOO_MANY_REQUESTS")


@pytest.mark.parametrize(
    "overrides",
    [{"consent": False}, {"consent": None}, {"email": "not-an-address"}, {"language": "eng"}, {"consent_text": ""}],
)
def test_invalid_body(api, products, quantities, overrides):
    payload = {key: value for key, value in body(**overrides).items() if value is not None}
    response = api.post(subscribe_url(), payload, format="json")
    assert (response.status_code, response.json()["error"]) == (400, "VALIDATION_ERROR")
    assert not Subscription.objects.exists()


def test_honeypot_answers_201_and_stores_nothing(api, products, quantities):
    response = api.post(subscribe_url(), body(website="https://spam.example"), format="json")
    assert (response.status_code, response.content) == (201, b'{"status":"saved"}')
    assert not Subscription.objects.exists()


def test_channel_without_templates_is_not_found(api, products, quantities, monkeypatch):
    monkeypatch.setattr(stock_settings, "PRODUCT_URL", {})
    assert api.post(subscribe_url(), body(), format="json").status_code == 404
    assert api.post(cancel_url(), {"token": "x"}, format="json").status_code == 404


def _token(products, quantities) -> tuple[Subscription, str]:
    row, _ = subscription_service.subscribe(subscribe_data())
    return row, token_service.make(row)


def test_cancel_with_a_valid_token(api, products, quantities):
    row, token = _token(products, quantities)
    for _ in range(2):  # again: the same 200
        response = api.post(cancel_url(), {"token": token}, format="json")
        assert (response.status_code, response.json()) == (200, {"status": "cancelled"})
    row.refresh_from_db()
    assert (row.status, row.cancel_reason) == (Status.CANCELLED, CancelReason.USER)


def test_tampered_token(api, products, quantities):
    row, token = _token(products, quantities)
    forged = signing.dumps([row.pk + 1, "0" * 16], salt="another-salt")
    for bad in (token[:-2] + "xx", forged, "garbage"):
        assert api.post(cancel_url(), {"token": bad}, format="json").status_code == 400
    row.refresh_from_db()
    assert row.status == Status.WAITING


def test_token_of_an_anonymised_row(api, products, quantities):
    _, token = _token(products, quantities)
    gdpr_erase(EMAIL)
    assert api.post(cancel_url(), {"token": token}, format="json").status_code == 400


def test_token_of_another_channel(api, products, quantities, monkeypatch):
    _, token = _token(products, quantities)
    monkeypatch.setattr(stock_settings, "PRODUCT_URL", {**stock_settings.PRODUCT_URL, "us-store": "{url_key}"})
    assert api.post(cancel_url("us-store"), {"token": token}, format="json").status_code == 400


@pytest.mark.skipif(not WITH_AGREEMENTS, reason="django_agreements is not installed")
def test_forwarded_ip_list_is_stored_as_no_ip(api, agreement, products, quantities):
    from django_agreements.models import ConsentRecord

    response = api.post(subscribe_url(), body(), format="json", HTTP_X_FORWARDED_FOR="1.2.3.4, 5.6.7.8")
    assert response.status_code == 201
    assert ConsentRecord.objects.get().ip_address is None  # DRF joins the list without NUM_PROXIES
