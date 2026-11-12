# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""The second record of a consent: a `ConsentRecord` in django_agreements, when it is installed and set up.

The only place that imports django_agreements, and only lazily. A missing app, a `None` slug, a missing definition
or one without a published version never blocks a request: the consent stays on the row only (a system check warns).
"""

import logging

from django.apps import apps
from django.core.exceptions import ObjectDoesNotExist

from django_stock_alerts import settings as stock_settings
from django_stock_alerts.models import Subscription

logger = logging.getLogger(__name__)

SOURCE = "stock_alerts"
_warned: set[str] = set()


def record_grant(subscription: Subscription, ip_address: str | None, user_agent: str) -> int | None:
    """The id of the written grant, or `None` when there is nowhere to write it."""
    return _record(subscription, granted=True, ip_address=ip_address, user_agent=user_agent)


def record_withdrawal(subscription: Subscription) -> None:
    _record(subscription, granted=False, ip_address=None, user_agent="")


def _record(subscription: Subscription, *, granted: bool, ip_address: str | None, user_agent: str) -> int | None:
    slug = stock_settings.AGREEMENT_SLUG
    if slug is None or not apps.is_installed("django_agreements"):
        return None
    from django_agreements.services.consent_service import record_consent

    try:
        record = record_consent(
            email=subscription.email,
            slug=slug,
            granted=granted,
            source=SOURCE,
            channel_idx=subscription.channel_idx,
            ip_address=ip_address,
            user_agent=user_agent,
        )
    except (ObjectDoesNotExist, ValueError):
        _warn_once(slug)
        return None
    return record.pk


def _warn_once(slug: str) -> None:
    if slug not in _warned:
        _warned.add(slug)
        logger.warning("stock alerts: agreement %r missing or unpublished, consents kept on the requests only", slug)
