# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""The one place that reads the catalogue (django_matrix): what a SKU is, how many pieces are saleable, what the
alert email shows and where its links lead. Links come only from the channel templates and matrix data."""

from dataclasses import dataclass
from urllib.parse import quote

from django.db.models import F, Prefetch, QuerySet
from django_matrix.enums import FeatureType, ProductType
from django_matrix.models import Attribute, ProductPrice, ProductRepresentation, ProductT9N
from django_matrix.services.stock_service import get_quantities

from django_stock_alerts import settings as stock_settings
from django_stock_alerts.models import Subscription
from django_stock_alerts.services import token_service

MIN_IMAGE_WIDTH = 240
_VARIANT_FEATURE_TYPES = (FeatureType.SELECT, FeatureType.MULTISELECT)


@dataclass(frozen=True)
class Product:
    sku: str
    parent_sku: str
    product_type: str


@dataclass(frozen=True)
class ProductCard:
    name: str
    variant_line: str | None
    image_path: str | None
    url_key: str
    price: str | None
    currency: str | None


def find(channel_idx: str, sku: str) -> Product | None:
    """A product a person can wait for; a configurable parent is never sold itself, only its variants are."""
    row = _sellable(channel_idx, sku).select_related("parent").first()
    if row is None:
        return None
    return Product(sku=row.sku, parent_sku=row.parent.sku if row.parent else "", product_type=row.product_type or "")


def saleable_quantity(channel_idx: str, sku: str) -> int:
    """A SKU without stock data is left out by `get_quantities`: it counts as 0, as the storefront reads it."""
    return get_quantities([sku], channel_idx).get(sku, 0)


def quantities(channel_idx: str, skus: list[str]) -> dict[str, int]:
    return get_quantities(skus, channel_idx)


def describe(channel_idx: str, sku: str, language: str, country: str = "") -> ProductCard | None:
    """What the email shows; `None` when the variant is gone from the channel. A fixed number of queries.

    Price: the channel's default currency, the row of `country` (iso2) when there is one, else the one without a
    country, else the first."""
    t9ns = ProductT9N.objects.filter(language__iso2=language)
    variant_attributes = Attribute.objects.filter(linking=True, feature_type__in=_VARIANT_FEATURE_TYPES).order_by("pk")
    row = (
        _sellable(channel_idx, sku)
        .select_related("parent", "channel__default_currency")
        .prefetch_related(
            Prefetch("t9ns", queryset=t9ns),
            Prefetch("parent__t9ns", queryset=t9ns),
            Prefetch("attributes", queryset=variant_attributes),
            Prefetch("prices", queryset=_prices_of_default_currency()),
        )
        .first()
    )
    return None if row is None else _card(row, language, country)


def product_url(subscription: Subscription, url_key: str) -> str:
    template = stock_settings.PRODUCT_URL[subscription.channel_idx]
    return template.format(country=subscription.country.lower(), url_key=_quote(url_key), sku=_quote(subscription.sku))


def cancel_url(subscription: Subscription) -> str:
    template = stock_settings.CANCEL_URL[subscription.channel_idx]
    token = _quote(token_service.make(subscription))
    return template.format(country=subscription.country.lower(), token=token, sku=_quote(subscription.sku))


def _quote(value: str) -> str:
    return quote(value, safe="")


def _sellable(channel_idx: str, sku: str) -> QuerySet:
    rows = ProductRepresentation.objects.filter(channel__idx=channel_idx, sku=sku)
    return rows.exclude(product_type=ProductType.PRODUCT_CONFIGURABLE)


def _prices_of_default_currency() -> QuerySet:
    prices = ProductPrice.objects.filter(currency_id=F("product_representation__channel__default_currency_id"))
    return prices.select_related("currency", "country").order_by(F("country_id").asc(nulls_first=True), "pk")


def _card(row: ProductRepresentation, language: str, country: str) -> ProductCard:
    own, parent = _t9n(row), _t9n(row.parent) if row.parent else None
    price = _price_for(row.prices.all(), country)
    money = _money(price)
    return ProductCard(
        name=(parent and parent.name) or (own and own.name) or row.sku,
        variant_line=_variant_line(row, language) if row.parent else None,
        image_path=_image_path(row.main_image) or _image_path(row.parent.main_image if row.parent else None),
        url_key=(parent and parent.url_key) or (own and own.url_key) or "",
        price=money,
        currency=price.currency.iso3 if money else None,
    )


def _price_for(prices: list, country: str) -> ProductPrice | None:
    of_country = [p for p in prices if p.country and p.country.iso2.lower() == country.lower()]
    return next(iter(of_country or prices), None)


def _t9n(row: ProductRepresentation) -> ProductT9N | None:
    return next(iter(row.t9ns.all()), None)


def _variant_line(row: ProductRepresentation, language: str) -> str | None:
    parts = [
        f"{(attribute.feature_name_t9n or {}).get(language) or attribute.feature_idx}: {_text(value)}"
        for attribute in row.attributes.all()
        if (value := attribute.attribute_value(language))
    ]
    return ", ".join(parts) or None


def _text(value: object) -> str:
    """A multiselect value comes as a list from the JSON column."""
    return ", ".join(map(str, value)) if isinstance(value, list) else str(value)


def _image_path(main_image: dict | None) -> str | None:
    """The smallest source at least `MIN_IMAGE_WIDTH` wide, else the widest one."""
    sources = [s for s in (main_image or {}).get("source_set") or [] if s.get("source")]
    if not sources:
        return None
    wide_enough = [s for s in sources if (s.get("width") or 0) >= MIN_IMAGE_WIDTH]
    if wide_enough:
        return min(wide_enough, key=lambda s: s["width"])["source"]
    return max(sources, key=lambda s: s.get("width") or 0)["source"]


def _money(price: ProductPrice | None) -> str | None:
    value = None if price is None else (price.final_gross if price.final_gross is not None else price.final_price)
    return None if value is None else f"{value:.2f}"
