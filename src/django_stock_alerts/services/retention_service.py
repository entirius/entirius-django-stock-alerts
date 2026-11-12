# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Daily retention: old waiting requests expire, closed requests lose the address after the anonymise period."""

from dataclasses import dataclass
from datetime import datetime, timedelta

from django.db.models import Q, QuerySet
from django.utils import timezone

from django_stock_alerts import settings as stock_settings
from django_stock_alerts.enums import Status
from django_stock_alerts.gdpr import anonymised_address
from django_stock_alerts.models import Subscription

BATCH = 1000


@dataclass(frozen=True)
class RetentionResult:
    expired: int
    anonymised: int


def run_retention() -> RetentionResult:
    now = timezone.now()
    return RetentionResult(expired=_expire(now), anonymised=_anonymise(now))


def _expire(now: datetime) -> int:
    cutoff = now - timedelta(days=stock_settings.WAITING_DAYS)
    stale = Subscription.objects.filter(status=Status.WAITING, created_at__lt=cutoff)
    total = 0
    while pks := list(stale.values_list("pk", flat=True)[:BATCH]):
        total += Subscription.objects.filter(pk__in=pks).update(status=Status.EXPIRED, modified_at=now)
    return total


def _closed_before(cutoff: datetime) -> QuerySet:
    """Closing time: `notified_at`, `cancelled_at`; an expired row was last written when it expired."""
    closed = (
        Q(status=Status.NOTIFIED, notified_at__lt=cutoff)
        | Q(status=Status.CANCELLED, cancelled_at__lt=cutoff)
        | Q(status=Status.EXPIRED, modified_at__lt=cutoff)
    )
    return Subscription.objects.filter(closed, anonymised_at__isnull=True)


def _anonymise(now: datetime) -> int:
    pending = _closed_before(now - timedelta(days=stock_settings.ANONYMISE_DAYS)).only("pk", "email")
    total = 0
    while rows := list(pending[:BATCH]):
        for row in rows:
            row.email, row.anonymised_at, row.modified_at = anonymised_address(row.email), now, now
        total += Subscription.objects.bulk_update(rows, ["email", "anonymised_at", "modified_at"])
    return total
