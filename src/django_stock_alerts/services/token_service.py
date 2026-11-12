# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Signed cancel tokens: the token is the credential of the public cancel route.

Payload = the row's pk and a 16-character keyed digest of its address, no max age. A row whose address changed
(anonymised) no longer matches its old links.
"""

import hmac

from django.core import signing
from django.utils.crypto import salted_hmac

from django_stock_alerts.models import Subscription

SALT = "stock-alerts.cancel"


class BadToken(Exception):
    """Bad signature, unknown row, or a row whose address no longer matches the token."""


def _digest(email: str) -> str:
    """Keyed with SECRET_KEY: the payload is readable, so a plain hash would let a link holder confirm a guessed address."""
    return salted_hmac(SALT, email).hexdigest()[:16]


def make(subscription: Subscription) -> str:
    return signing.dumps([subscription.pk, _digest(subscription.email)], salt=SALT)


def read(token: str) -> Subscription:
    try:
        pk, digest = signing.loads(token, salt=SALT)
        subscription = Subscription.objects.get(pk=pk)
    except (signing.BadSignature, ValueError, TypeError, Subscription.DoesNotExist) as exc:
        raise BadToken from exc
    if not hmac.compare_digest(str(digest), _digest(subscription.email)):
        raise BadToken
    return subscription
