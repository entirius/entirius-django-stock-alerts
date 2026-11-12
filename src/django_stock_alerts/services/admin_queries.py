# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
"""Reads of the admin panel: demand per variant, the request list, the export; the admin cancel.

Product names and variant lines come in one batched catalogue read per page (`describe`), never per row, in the
channel's default language. The callers validate `ordering` against the schema's allowlist; the maps below only
translate an allowed key into `order_by` fields.
"""

from collections.abc import Iterable, Iterator
from dataclasses import dataclass
from datetime import timedelta

from django.db import transaction
from django.db.models import Count, Max, Min, Prefetch, Q, QuerySet, Sum
from django.utils import timezone
from django_matrix.enums import FeatureType, ProductType
from django_matrix.models import Attribute, Channel, ProductRepresentation, ProductT9N
from django_matrix.services.stock_service import get_quantities

from django_stock_alerts.enums import CancelReason, Status
from django_stock_alerts.models import Subscription
from django_stock_alerts.services import subscription_service

NOTIFIED_WINDOW = timedelta(days=30)
_VARIANT_FEATURE_TYPES = (FeatureType.SELECT, FeatureType.MULTISELECT)
_DEMAND_ORDERING = {
    "waiting": ("waiting", "sku"),
    "-waiting": ("-waiting", "sku"),
    "oldest_request": ("oldest_request", "sku"),
    "-oldest_request": ("-oldest_request", "sku"),
    "sku": ("sku",),
}
_SUBSCRIPTION_ORDERING = {
    "created": ("created_at", "pk"),
    "-created": ("-created_at", "-pk"),
    "notified_at": ("notified_at", "pk"),
    "-notified_at": ("-notified_at", "-pk"),
}


@dataclass(frozen=True)
class Description:
    name: str | None
    variant_line: str | None


UNKNOWN = Description(name=None, variant_line=None)


@dataclass(frozen=True)
class SubscriptionFilters:
    status: str | None = None
    sku: str = ""
    search: str = ""
    ordering: str = "-created"


def demand(channel_idx: str, search: str, ordering: str) -> QuerySet:
    """One row per waited-for SKU: `sku`, `parent_sku`, `waiting`, `oldest_request`, `notified_30d`."""
    since = timezone.now() - NOTIFIED_WINDOW
    waiting = Q(status=Status.WAITING)
    rows = Subscription.objects.filter(channel_idx=channel_idx)
    if search:
        rows = rows.filter(Q(sku__startswith=search) | Q(sku__in=_skus_named(channel_idx, search)))
    rows = rows.values("sku").annotate(
        parent_sku=Max("parent_sku"),
        waiting=Count("pk", filter=waiting),
        oldest_request=Min("created_at", filter=waiting),
        notified_30d=Count("pk", filter=Q(status=Status.NOTIFIED, notified_at__gte=since)),
    )
    return rows.filter(waiting__gt=0).order_by(*_DEMAND_ORDERING[ordering])


def total_waiting(rows: QuerySet) -> int:
    """Requests waiting across a `demand` queryset."""
    return rows.order_by().aggregate(total=Sum("waiting"))["total"] or 0


def subscriptions(channel_idx: str, filters: SubscriptionFilters) -> QuerySet:
    rows = Subscription.objects.filter(channel_idx=channel_idx)
    if filters.status:
        rows = rows.filter(status=filters.status)
    if filters.sku:
        rows = rows.filter(sku=filters.sku)
    if filters.search:
        address = subscription_service.normalise_email(filters.search)
        rows = rows.filter(Q(email=address) | Q(sku__startswith=filters.search))
    return rows.order_by(*_SUBSCRIPTION_ORDERING[filters.ordering])


def quantities(channel_idx: str, skus: list[str]) -> dict[str, int]:
    """Saleable pieces per SKU; a SKU without stock data is 0."""
    found = get_quantities(skus, channel_idx) if skus else {}
    return {sku: found.get(sku, 0) for sku in skus}


def describe(channel_idx: str, skus: Iterable[str]) -> dict[str, Description]:
    """Name and variant line per SKU in the channel's default language; a fixed number of queries for any page."""
    skus = list(set(skus))
    if not skus:
        return {}
    language = _default_language(channel_idx)
    t9ns = ProductT9N.objects.filter(language__iso2=language)
    variant_attributes = Attribute.objects.filter(linking=True, feature_type__in=_VARIANT_FEATURE_TYPES).order_by("pk")
    rows = (
        ProductRepresentation.objects.filter(channel__idx=channel_idx, sku__in=skus)
        .exclude(product_type=ProductType.PRODUCT_CONFIGURABLE)
        .select_related("parent")
        .prefetch_related(
            Prefetch("t9ns", t9ns),
            Prefetch("parent__t9ns", t9ns),
            Prefetch("attributes", variant_attributes),
        )
    )
    return {row.sku: _description(row, language) for row in rows}


def subscriptions_described(channel_idx: str, rows: QuerySet, chunk: int = 500) -> Iterator[tuple]:
    """`(row, description)` pairs streamed in chunks: one catalogue read per chunk, for the export."""
    batch: list[Subscription] = []
    for row in rows.iterator(chunk_size=chunk):
        batch.append(row)
        if len(batch) == chunk:
            yield from _with_descriptions(channel_idx, batch)
            batch = []
    yield from _with_descriptions(channel_idx, batch)


def cancel(channel_idx: str, pk: int) -> Subscription:
    """Cancel by staff; a closed row comes back unchanged. `Subscription.DoesNotExist` for a row of another channel."""
    with transaction.atomic():
        row = Subscription.objects.select_for_update().get(channel_idx=channel_idx, pk=pk)
        return subscription_service.cancel(row, CancelReason.ADMIN)


def _with_descriptions(channel_idx: str, batch: list[Subscription]) -> Iterator[tuple]:
    described = describe(channel_idx, (row.sku for row in batch))
    return ((row, described.get(row.sku, UNKNOWN)) for row in batch)


def _skus_named(channel_idx: str, search: str) -> QuerySet:
    named = Q(t9ns__name__icontains=search) | Q(parent__t9ns__name__icontains=search)
    return ProductRepresentation.objects.filter(named, channel__idx=channel_idx).values("sku")


def _default_language(channel_idx: str) -> str | None:
    return Channel.objects.filter(idx=channel_idx).values_list("default_language__iso2", flat=True).first()


def _description(row: ProductRepresentation, language: str | None) -> Description:
    own = next(iter(row.t9ns.all()), None)
    parent = next(iter(row.parent.t9ns.all()), None) if row.parent else None
    return Description(
        name=(parent and parent.name) or (own and own.name) or None,
        variant_line=_variant_line(row, language) if row.parent else None,
    )


def _variant_line(row: ProductRepresentation, language: str | None) -> str | None:
    parts = [
        f"{(attribute.feature_name_t9n or {}).get(language) or attribute.feature_idx}: {_text(value)}"
        for attribute in row.attributes.all()
        if (value := attribute.attribute_value(language or ""))
    ]
    return ", ".join(parts) or None


def _text(value: object) -> str:
    """A multiselect value comes as a list from the JSON column."""
    return ", ".join(map(str, value)) if isinstance(value, list) else str(value)
