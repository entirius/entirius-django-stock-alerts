# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
from unittest.mock import patch

import pytest
from django.apps import apps
from django.core.cache import cache
from django.core.management import call_command
from django_matrix.enums import ProductType
from django_matrix.models import Channel, ProductRepresentation
from rest_framework.test import APIClient

from django_stock_alerts.services.subscription_service import SubscribeData

CHANNEL_IDX = "default-europe"
PARENT_SKU, SKU, SKU_2 = "TSHIRT", "TSHIRT-RED-M", "TSHIRT-RED-L"
EMAIL = "anna@example.com"
WITH_ACCESS = apps.is_installed("django_access")
WITH_AGREEMENTS = apps.is_installed("django_agreements")


@pytest.fixture(autouse=True)
def _clear_cache():
    cache.clear()  # throttle counters


@pytest.fixture
def products(db):
    channel = Channel.objects.create(idx=CHANNEL_IDX, label="Europe")
    parent = ProductRepresentation.objects.create(
        sku=PARENT_SKU, channel=channel, product_type=ProductType.PRODUCT_CONFIGURABLE
    )
    for sku in (SKU, SKU_2):
        ProductRepresentation.objects.create(sku=sku, channel=channel, parent=parent)
    return channel


@pytest.fixture
def quantities():
    """Saleable quantity per SKU, as matrix reports it; a SKU left out counts as 0."""
    stock: dict[str, int] = {}
    with patch(
        "django_stock_alerts.services.catalog.get_quantities",
        side_effect=lambda skus, _: {sku: stock[sku] for sku in skus if sku in stock},
    ):
        yield stock


@pytest.fixture
def agreement(db):
    if not WITH_AGREEMENTS:
        pytest.skip("django_agreements is not installed")
    call_command("loaddata", "stock_alerts_agreement", verbosity=0)


@pytest.fixture
def subscribe_key(db) -> str | None:
    """A channel key with the subscribe scope where access is installed; `None` (no key needed) without it."""
    if not WITH_ACCESS:
        return None
    from django_access.models import Application
    from django_access.services.access_service import Actor
    from django_access.services.tokens import issue_token

    application = Application.objects.create(name="stock-alerts-tests")
    _, raw = issue_token(application, scopes=["stock_alerts.subscribe"], channel_idx=CHANNEL_IDX, actor=Actor())
    return raw


@pytest.fixture
def api(subscribe_key) -> APIClient:
    client = APIClient(HTTP_USER_AGENT="pytest-agent")
    if subscribe_key:
        client.credentials(HTTP_X_API_KEY=subscribe_key)
    return client


def subscribe_data(**overrides) -> SubscribeData:
    fields = {
        "channel_idx": CHANNEL_IDX,
        "sku": SKU,
        "email": EMAIL,
        "language": "en",
        "country": "pl",
        "consent_text": "Email me when it is back.",
        "ip_address": "203.0.113.7",
        "user_agent": "pytest-agent",
    }
    return SubscribeData(**{**fields, **overrides})


def body(**overrides) -> dict:
    fields = {
        "email": EMAIL,
        "sku": SKU,
        "language": "en",
        "country": "pl",
        "consent": True,
        "consent_text": "Email me when it is back.",
    }
    return {**fields, **overrides}


def subscribe_url(channel_idx: str = CHANNEL_IDX) -> str:
    return f"/api/stock-alerts/v2/{channel_idx}/subscriptions/"


def cancel_url(channel_idx: str = CHANNEL_IDX) -> str:
    return f"/api/stock-alerts/v2/{channel_idx}/subscriptions/cancel/"


@pytest.fixture
def agreement_if_installed(db):
    if WITH_AGREEMENTS:
        call_command("loaddata", "stock_alerts_agreement", verbosity=0)


@pytest.fixture
def mailbox(db, settings):
    """django_email channel of the matrix channel (same idx), languages, and the locmem outbox."""
    from django.core import mail
    from django_email.models import Channel as EmailChannel
    from django_email.models import LangChannelConfig
    from django_regional.models import Language

    settings.EMAIL_BACKEND = "django.core.mail.backends.locmem.EmailBackend"
    channel = EmailChannel.objects.create(idx=CHANNEL_IDX, label="Europe", from_email="shop@example.com")
    LangChannelConfig.objects.create(channel=channel, language=None, shop_name="Sample Shop")
    for iso2 in ("pl", "en"):
        Language.objects.get_or_create(
            iso2=iso2, defaults={"iso3": f"{iso2}x", "name_en": iso2, "name_pl": iso2, "name_source": iso2}
        )
    mail.outbox = []
    return mail.outbox


def make_row(**overrides):
    """A waiting request saved directly (no consent bridge, no stock read)."""
    from django.utils import timezone

    from django_stock_alerts.models import Subscription

    fields = {
        "channel_idx": CHANNEL_IDX,
        "sku": SKU,
        "parent_sku": PARENT_SKU,
        "email": EMAIL,
        "language": "en",
        "country": "pl",
        "consent_at": timezone.now(),
        "consent_text": "Email me when it is back.",
    }
    return Subscription.objects.create(**{**fields, **overrides})
