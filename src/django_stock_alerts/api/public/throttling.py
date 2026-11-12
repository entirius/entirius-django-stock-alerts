# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Throttles of the public routes.

``DEFAULT_THROTTLE_RATES[<scope>]`` overrides a rate; the class ``fallback_rate`` is the safety net when the scope
is unset or malformed. The fallback must not live in a class ``rate``: DRF's ``SimpleRateThrottle.__init__`` skips
``get_rate()`` when ``rate`` is set, which would silently disable the settings override.
"""

import hashlib
import re

from django.core.exceptions import ImproperlyConfigured
from django_utils.api.client_ip import ClientIPThrottleMixin
from rest_framework.throttling import AnonRateThrottle, SimpleRateThrottle

# What DRF's parse_rate reads without raising: "<count>/<s|m|h|d...>".
_RATE = re.compile(r"\d+/[smhd]\w*")


class _FallbackRateMixin:
    fallback_rate: str

    def __init__(self) -> None:
        self.rate = self.get_rate()
        super().__init__()

    def get_rate(self) -> str:
        try:
            rate = super().get_rate()
        except ImproperlyConfigured:  # scope missing from DEFAULT_THROTTLE_RATES
            return self.fallback_rate
        if not isinstance(rate, str) or not _RATE.fullmatch(rate):  # a malformed rate must not disable throttling
            return self.fallback_rate
        return rate


class _ClientThrottle(ClientIPThrottleMixin, _FallbackRateMixin, AnonRateThrottle):
    """Per client address: ``settings.CLIENT_IP_HEADER`` when set (behind a proxy), DRF ``get_ident`` otherwise."""


class SubscribeThrottle(_ClientThrottle):
    scope = "stock_alerts_subscribe"
    fallback_rate = "10/min"


class SubscribeAddressThrottle(_FallbackRateMixin, SimpleRateThrottle):
    """Per e-mail address, whoever asks; the cache key carries a digest of the address, never the address."""

    scope = "stock_alerts_subscribe_address"
    fallback_rate = "6/hour"

    def get_cache_key(self, request, view) -> str | None:
        email = request.data.get("email") if hasattr(request.data, "get") else None
        if not isinstance(email, str) or not email.strip():
            return None  # a refused body stores nothing; the per-client throttle still counts it
        digest = hashlib.sha256(email.strip().lower().encode()).hexdigest()
        return self.cache_format % {"scope": self.scope, "ident": digest}


class CancelThrottle(_ClientThrottle):
    scope = "stock_alerts_cancel"
    fallback_rate = "20/min"
