# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""GDPR hooks (art. 15 export, art. 17 erasure), discovered by `django_leads.gdpr.registry`.

Erasure replaces the address with the platform's anonymised token on every row of the person first, then cancels
the waiting ones (reason `erased`): the withdrawal written to django_agreements already carries the token, so it
leaks no address whichever erase hook runs first. Rows stay as the record of what was requested and consented.
"""

import hashlib
from typing import Any

from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from django_stock_alerts import settings as stock_settings
from django_stock_alerts.enums import CancelReason, Status
from django_stock_alerts.models import Subscription
from django_stock_alerts.services import subscription_service

EXPORT_FIELDS = ("id", "channel_idx", "sku", "parent_sku", "email", "language", "country", "status", "consent_at",
                 "consent_text", "consent_record_id", "notified_at", "cancelled_at", "cancel_reason", "created_at",
                 "anonymised_at")  # fmt: skip


def anonymised_address(email: str) -> str:
    """Same token as `django_leads.utils.emails.anonymised_address` (never import across; a test pins the parity)."""
    digest = hashlib.sha256((email or "").strip().lower().encode()).hexdigest()
    return f"anon-{digest[:16]}@{stock_settings.ANONYMISED_DOMAIN}"


def _of_email(email: str) -> Q:
    """The plain address, or its token after an earlier erasure or retention."""
    return Q(email=subscription_service.normalise_email(email)) | Q(email=anonymised_address(email))


def gdpr_export(email: str) -> dict[str, Any]:
    return {"Subscription": list(Subscription.objects.filter(_of_email(email)).values(*EXPORT_FIELDS))}


def gdpr_erase(email: str) -> dict[str, int]:
    plain, token = subscription_service.normalise_email(email), anonymised_address(email)
    with transaction.atomic():
        erased = Subscription.objects.filter(email=plain).update(email=token, anonymised_at=timezone.now())
        waiting = Subscription.objects.select_for_update().filter(email=token, status=Status.WAITING)
        for subscription in waiting:
            subscription_service.cancel(subscription, CancelReason.ERASED)
    return {"subscriptions": erased}
