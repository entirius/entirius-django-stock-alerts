# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Configuration checks (tag `entirius_config`, aggregated by django-munin).

A database not migrated yet (first `migrate`) skips the checks that read it.
"""

from django.apps import apps
from django.core import checks
from django.db import DatabaseError

from django_stock_alerts import settings as stock_settings
from django_stock_alerts.enums import Status
from django_stock_alerts.models import Subscription

TAG = "entirius_config"
NO_TEMPLATES = "stock_alerts.W001"
BAD_TEMPLATE = "stock_alerts.E002"
NO_AGREEMENT = "stock_alerts.W003"
_PLACEHOLDERS = (("STOCK_ALERTS_PRODUCT_URL", "{url_key}"), ("STOCK_ALERTS_CANCEL_URL", "{token}"))


@checks.register(TAG)
def templates_complete(app_configs=None, **kwargs) -> list[checks.CheckMessage]:
    """A template without its placeholder sends every person a link that leads nowhere."""
    templates = {
        "STOCK_ALERTS_PRODUCT_URL": stock_settings.PRODUCT_URL,
        "STOCK_ALERTS_CANCEL_URL": stock_settings.CANCEL_URL,
    }
    return [
        checks.Error(f"{name}[{channel_idx!r}] lacks {placeholder}", id=BAD_TEMPLATE)
        for name, placeholder in _PLACEHOLDERS
        for channel_idx, template in templates[name].items()
        if placeholder not in template
    ]


@checks.register(TAG)
def waiting_channels_configured(app_configs=None, **kwargs) -> list[checks.CheckMessage]:
    """Waiting requests of a channel without its URL templates can never be sent."""
    try:
        channels = set(Subscription.objects.filter(status=Status.WAITING).values_list("channel_idx", flat=True))
    except DatabaseError:
        return []
    configured = set(stock_settings.PRODUCT_URL) & set(stock_settings.CANCEL_URL)
    return [
        checks.Warning(
            f"Channel {channel_idx!r} has waiting back-in-stock requests and no URL templates",
            hint="Set STOCK_ALERTS_PRODUCT_URL and STOCK_ALERTS_CANCEL_URL for the channel.",
            id=NO_TEMPLATES,
        )
        for channel_idx in sorted(channels - configured)
    ]


@checks.register(TAG)
def agreement_published(app_configs=None, **kwargs) -> list[checks.CheckMessage]:
    slug = stock_settings.AGREEMENT_SLUG
    if slug is None or not apps.is_installed("django_agreements"):
        return []
    from django_agreements.models import AgreementVersion

    try:
        published = AgreementVersion.objects.filter(definition__slug=slug, is_current=True).exists()
    except DatabaseError:
        return []
    if published:
        return []
    hint = f"Load the fixture stock_alerts_agreement or publish a version of {slug!r}."
    return [
        checks.Warning(
            f"Agreement {slug!r} has no published version: consents are kept on the requests only",
            hint=hint,
            id=NO_AGREEMENT,
        )
    ]
