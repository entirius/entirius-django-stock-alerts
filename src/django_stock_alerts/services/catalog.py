# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""The one place that reads the catalogue (django_matrix): what a SKU is and how many pieces are saleable."""

from dataclasses import dataclass

from django_matrix.enums import ProductType
from django_matrix.models import ProductRepresentation
from django_matrix.services.stock_service import get_quantities


@dataclass(frozen=True)
class Product:
    sku: str
    parent_sku: str
    product_type: str


def find(channel_idx: str, sku: str) -> Product | None:
    """A product a person can wait for; a configurable parent is never sold itself, only its variants are."""
    rows = ProductRepresentation.objects.filter(channel__idx=channel_idx, sku=sku)
    row = rows.exclude(product_type=ProductType.PRODUCT_CONFIGURABLE).select_related("parent").first()
    if row is None:
        return None
    return Product(sku=row.sku, parent_sku=row.parent.sku if row.parent else "", product_type=row.product_type or "")


def saleable_quantity(channel_idx: str, sku: str) -> int:
    """A SKU without stock data is left out by `get_quantities`: it counts as 0, as the storefront reads it."""
    return get_quantities([sku], channel_idx).get(sku, 0)
