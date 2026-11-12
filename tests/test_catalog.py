# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
from decimal import Decimal

import pytest
from django_matrix.enums import FeatureType
from django_matrix.models import Attribute, ProductPrice, ProductRepresentation, ProductT9N
from django_regional.models import Currency, Language

from django_stock_alerts import settings as stock_settings
from django_stock_alerts.services import catalog, token_service

from .conftest import CHANNEL_IDX, PARENT_SKU, SKU, SKU_2, make_row

IMAGE = {
    "source_set": [
        {"width": 1024, "source": "/media/big.webp"},
        {"width": 160, "source": "/media/small.webp"},
        {"width": 320, "source": "/media/card.webp"},
    ]
}


def _language(iso2: str) -> Language:
    lang, _ = Language.objects.get_or_create(
        iso2=iso2, defaults={"iso3": f"{iso2}x", "name_en": iso2, "name_pl": iso2, "name_source": iso2}
    )
    return lang


@pytest.fixture
def catalogue(products):
    """Parent with names in pl/en and a picture; the child with a size, a price in the channel currency and another."""
    pln, _ = Currency.objects.get_or_create(iso3="PLN", defaults={"name_en": "Zloty", "name_pl": "Złoty"})
    eur, _ = Currency.objects.get_or_create(iso3="EUR", defaults={"name_en": "Euro", "name_pl": "Euro"})
    products.default_currency = pln
    products.save()
    parent = ProductRepresentation.objects.get(sku=PARENT_SKU)
    parent.main_image = IMAGE
    parent.save()
    child = ProductRepresentation.objects.get(sku=SKU)
    for iso2, name in (("en", "Red T-shirt"), ("pl", "Czerwona koszulka")):
        ProductT9N.objects.create(
            product_representation=parent, language=_language(iso2), name=name, url_key=f"{iso2} tee/x"
        )
        ProductT9N.objects.create(product_representation=child, language=_language(iso2), name=f"{name} M")
    Attribute.objects.create(
        product=child,
        feature_idx="size",
        feature_type=FeatureType.SELECT,
        feature_name_t9n={"en": "Size", "pl": "Rozmiar"},
        attribute_idx="m",
        attribute_value_text="M",
        linking=True,
    )
    ProductPrice.objects.create(product_representation=child, currency=eur, final_gross=Decimal("30"))
    ProductPrice.objects.create(product_representation=child, currency=pln, final_gross=Decimal("129"))
    return child


def test_describe_a_variant(catalogue):
    card = catalog.describe(CHANNEL_IDX, SKU, "pl")

    assert card == catalog.ProductCard(
        name="Czerwona koszulka",
        variant_line="Rozmiar: M",
        image_path="/media/card.webp",
        url_key="pl tee/x",
        price="129.00",
        currency="PLN",
    )


def test_describe_falls_back_without_data(products):
    card = catalog.describe(CHANNEL_IDX, SKU_2, "en")

    assert card == catalog.ProductCard(
        name=SKU_2, variant_line=None, image_path=None, url_key="", price=None, currency=None
    )


def test_describe_a_product_gone_or_a_parent(products):
    assert catalog.describe(CHANNEL_IDX, "GONE", "en") is None
    assert catalog.describe(CHANNEL_IDX, PARENT_SKU, "en") is None


def test_describe_runs_a_fixed_number_of_queries(catalogue, django_assert_max_num_queries):
    with django_assert_max_num_queries(5):
        catalog.describe(CHANNEL_IDX, SKU, "en")


def test_child_picture_wins_and_a_small_one_is_the_widest(catalogue):
    catalogue.main_image = {"source_set": [{"width": 100, "source": "/a.jpg"}, {"width": 200, "source": "/b.jpg"}]}
    catalogue.save()

    assert catalog.describe(CHANNEL_IDX, SKU, "en").image_path == "/b.jpg"


def test_product_url_quotes_url_key_and_sku(products):
    row = make_row(sku="A B/1&x", country="PL")

    url = catalog.product_url(row, "red tee/ü")

    assert url == "https://shop.example/pl/product/red%20tee%2F%C3%BC?variant=A%20B%2F1%26x"


def test_template_without_country(products, monkeypatch):
    monkeypatch.setitem(stock_settings.PRODUCT_URL, CHANNEL_IDX, "https://shop.example/p/{url_key}?v={sku}")
    monkeypatch.setitem(stock_settings.CANCEL_URL, CHANNEL_IDX, "https://shop.example/cancel?t={token}")
    row = make_row()

    assert catalog.product_url(row, "tee") == f"https://shop.example/p/tee?v={SKU}"
    assert catalog.cancel_url(row).startswith("https://shop.example/cancel?t=")


def test_cancel_url_carries_a_readable_token(products):
    row = make_row()

    url = catalog.cancel_url(row)

    from urllib.parse import parse_qs, urlsplit

    token = parse_qs(urlsplit(url).query)["token"][0]
    assert url.startswith("https://shop.example/pl/stock-alert/cancel?token=")
    assert token_service.read(token) == row
