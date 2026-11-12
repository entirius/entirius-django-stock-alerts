# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
"""Admin API fixtures: a catalogue with names and a size, request rows saved directly, staff clients with a JWT."""

import itertools

import pytest
from django.contrib.auth import get_user_model
from django.utils import timezone
from django_matrix.enums import FeatureType
from django_matrix.models import Attribute, ProductRepresentation, ProductT9N
from django_regional.models import Language
from rest_framework.test import APIClient
from rest_framework_simplejwt.tokens import AccessToken

from django_stock_alerts.models import Subscription
from tests.conftest import CHANNEL_IDX, EMAIL, PARENT_SKU, SKU, WITH_ACCESS

_names = itertools.count()


def admin_url(tail: str, channel_idx: str = CHANNEL_IDX) -> str:
    return f"/api/stock-alerts/v2/admin/{channel_idx}/{tail}"


def make_row(**overrides) -> Subscription:
    """A request saved directly: no consent bridge, no stock read."""
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


def _language(iso2: str) -> Language:
    defaults = {"iso3": f"{iso2}x", "name_en": iso2, "name_pl": iso2, "name_source": iso2}
    return Language.objects.get_or_create(iso2=iso2, defaults=defaults)[0]


@pytest.fixture
def catalogue(products):
    """Channel default language en; the parent named in en and pl, the child with size M."""
    products.default_language = _language("en")
    products.save()
    parent = ProductRepresentation.objects.get(sku=PARENT_SKU)
    child = ProductRepresentation.objects.get(sku=SKU)
    for iso2, name in (("en", "Red T-shirt"), ("pl", "Czerwona koszulka")):
        ProductT9N.objects.create(product_representation=parent, language=_language(iso2), name=name)
    Attribute.objects.create(
        product=child,
        feature_idx="size",
        feature_type=FeatureType.SELECT,
        feature_name_t9n={"en": "Size", "pl": "Rozmiar"},
        attribute_value_text="M",
        linking=True,
    )
    return products


def _client(user) -> APIClient:
    client = APIClient()
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {AccessToken.for_user(user)}")
    return client


def _user(**flags):
    defaults = {"username": f"staff{next(_names)}", "is_staff": True, "is_active": True}
    return get_user_model().objects.create_user(**{**defaults, **flags})


def _granted(role_key: str):
    user = _user()
    if WITH_ACCESS:
        from django_access.models import Role
        from django_access.services.access_service import Actor, grant_role

        grant_role(Role.objects.get(key=role_key), user=user, actor=Actor())
    return user


@pytest.fixture
def staff(db) -> APIClient:
    """A Manager: write on every area."""
    return _client(_granted("manager"))


@pytest.fixture
def viewer(db) -> APIClient:
    """Read on every area."""
    return _client(_granted("viewer"))


@pytest.fixture
def make_client(db):
    """`make_client(**user_flags)` → a client of a fresh user without a role."""
    return lambda **flags: _client(_user(**flags))
