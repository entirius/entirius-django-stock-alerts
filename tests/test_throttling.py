# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
import pytest
from rest_framework.throttling import SimpleRateThrottle

from django_stock_alerts.api.public.throttling import CancelThrottle, SubscribeAddressThrottle, SubscribeThrottle
from tests.conftest import body, cancel_url, subscribe_url

pytestmark = pytest.mark.django_db


@pytest.fixture
def rates(monkeypatch):
    """DEFAULT_THROTTLE_RATES as SimpleRateThrottle reads it (a class attribute bound at import)."""

    def set_rates(values: dict):
        monkeypatch.setattr(SimpleRateThrottle, "THROTTLE_RATES", values)

    return set_rates


@pytest.mark.parametrize("throttle", [SubscribeThrottle, SubscribeAddressThrottle, CancelThrottle])
@pytest.mark.parametrize("configured", ["unset", "malformed", "ten/min", "10/", "10/x", None, ""])
def test_unset_or_malformed_rate_falls_back(rates, throttle, configured):
    rates({} if configured == "unset" else {throttle.scope: configured})
    assert throttle().rate == throttle.fallback_rate


def test_configured_rate_wins(rates):
    rates({SubscribeThrottle.scope: "99/day"})
    assert SubscribeThrottle().rate == "99/day"


def test_subscribe_per_client(api, products, quantities, rates):
    rates({SubscribeThrottle.scope: "2/min"})
    codes = [api.post(subscribe_url(), body(email=f"p{i}@example.com"), format="json").status_code for i in range(3)]
    assert codes == [201, 201, 429]


def test_subscribe_per_address(api, products, quantities, rates):
    rates({SubscribeAddressThrottle.scope: "2/hour"})
    codes = [
        api.post(subscribe_url(), body(), format="json", REMOTE_ADDR=f"198.51.100.{i}").status_code for i in range(3)
    ]
    assert codes == [201, 201, 429]


def test_cancel_per_client(api, products, quantities, rates):
    rates({CancelThrottle.scope: "2/min"})
    codes = [api.post(cancel_url(), {"token": "x"}, format="json").status_code for _ in range(3)]
    assert codes == [400, 400, 429]
