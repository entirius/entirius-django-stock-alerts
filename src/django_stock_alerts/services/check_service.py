# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Restock check: which waited-for SKUs can be bought again, and who gets the next wave of alerts.

Reads quantities for SKUs with waiting rows only, never the catalogue. A wave is the oldest waiting rows of a SKU
that no wave claimed in the last `CLAIM_TTL`, `quantity × STOCK_ALERTS_WAVE_FACTOR` of them (factor 0: all); the claim
is set before the send tasks are enqueued, and the send task re-checks the stock under a row lock.
"""

from collections.abc import Callable, Iterator
from dataclasses import dataclass, field
from datetime import timedelta

from django.db.models import Q
from django.utils import timezone

from django_stock_alerts import settings as stock_settings
from django_stock_alerts.enums import Status
from django_stock_alerts.models import Subscription
from django_stock_alerts.services import catalog

CLAIM_TTL = timedelta(minutes=30)


@dataclass
class CheckResult:
    channels: list[str] = field(default_factory=list)
    skus: int = 0
    back: int = 0
    enqueued: int = 0


def run_check(enqueue: Callable[[int], object]) -> CheckResult:
    """One pass over every channel with URL templates; `enqueue(pk)` schedules one alert."""
    result = CheckResult(channels=sorted(set(stock_settings.PRODUCT_URL) & set(stock_settings.CANCEL_URL)))
    for channel_idx in result.channels:
        for batch in _waiting_sku_batches(channel_idx):
            result.skus += len(batch)
            back = {sku: qty for sku, qty in catalog.quantities(channel_idx, batch).items() if qty >= 1}
            result.back += len(back)
            for sku, quantity in back.items():
                result.enqueued += _start_wave(channel_idx, sku, quantity, enqueue)
    return result


def _waiting_sku_batches(channel_idx: str) -> Iterator[list[str]]:
    waiting = Subscription.objects.filter(channel_idx=channel_idx, status=Status.WAITING)
    skus = list(waiting.order_by("sku").values_list("sku", flat=True).distinct())
    size = max(stock_settings.CHECK_BATCH, 1)
    for start in range(0, len(skus), size):
        yield skus[start : start + size]


def _start_wave(channel_idx: str, sku: str, quantity: int, enqueue: Callable[[int], object]) -> int:
    now = timezone.now()
    unclaimed = Q(wave_claimed_at__isnull=True) | Q(wave_claimed_at__lt=now - CLAIM_TTL)
    rows = Subscription.objects.filter(unclaimed, channel_idx=channel_idx, sku=sku, status=Status.WAITING)
    rows = rows.order_by("created_at", "pk").values_list("pk", flat=True)
    factor = stock_settings.WAVE_FACTOR
    pks = list(rows[: quantity * factor] if factor else rows)
    Subscription.objects.filter(pk__in=pks).update(wave_claimed_at=now, modified_at=now)
    for pk in pks:
        enqueue(pk)
    return len(pks)
