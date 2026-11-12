# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""The only writer of `Subscription`: save a request, cancel it.

The partial unique index on (channel, sku, email) of waiting rows is the only uniqueness guard; `subscribe` catches
its race inside a savepoint and returns the row the other request saved. Addresses are compared and stored
lower-cased. Logs carry the row pk, never the address.
"""

import logging
from dataclasses import dataclass

from django.db import IntegrityError, transaction
from django.utils import timezone

from django_stock_alerts import settings as stock_settings
from django_stock_alerts.enums import CancelReason, Status
from django_stock_alerts.models import Subscription
from django_stock_alerts.services import catalog, consent_bridge, token_service

logger = logging.getLogger(__name__)

# A withdrawal in agreements only when the person (or their erasure) ended the request.
_WITHDRAWING_REASONS = frozenset({CancelReason.USER, CancelReason.ERASED})


class ChannelClosed(Exception):
    """The channel has no product URL template: it accepts no requests."""


class ProductNotFound(Exception):
    pass


class InStock(Exception):
    pass


class TooManyRequests(Exception):
    """The address waits for `STOCK_ALERTS_MAX_WAITING_PER_EMAIL` variants in the channel already."""


@dataclass(frozen=True)
class SubscribeData:
    channel_idx: str
    sku: str
    email: str
    language: str
    country: str
    consent_text: str
    ip_address: str | None
    user_agent: str


def normalise_email(email: str) -> str:
    return email.strip().lower()


def ensure_channel_open(channel_idx: str) -> None:
    if channel_idx not in stock_settings.PRODUCT_URL:
        raise ChannelClosed


def subscribe(data: SubscribeData) -> tuple[Subscription, bool]:
    """The waiting row of (channel, sku, address) and whether this call created it."""
    ensure_channel_open(data.channel_idx)
    product = catalog.find(data.channel_idx, data.sku)
    if product is None:
        raise ProductNotFound
    if catalog.saleable_quantity(data.channel_idx, data.sku) > 0:
        raise InStock
    email = normalise_email(data.email)
    with transaction.atomic():
        if existing := _waiting(data.channel_idx, data.sku, email):
            return existing, False
        _check_cap(data.channel_idx, email)
        return _create(data, product, email)


def _waiting(channel_idx: str, sku: str, email: str) -> Subscription | None:
    return Subscription.objects.filter(channel_idx=channel_idx, sku=sku, email=email, status=Status.WAITING).first()


def _check_cap(channel_idx: str, email: str) -> None:
    waiting = Subscription.objects.filter(channel_idx=channel_idx, email=email, status=Status.WAITING).count()
    if waiting >= stock_settings.MAX_WAITING_PER_EMAIL:
        raise TooManyRequests


def _create(data: SubscribeData, product: catalog.Product, email: str) -> tuple[Subscription, bool]:
    try:
        with transaction.atomic():
            row = Subscription.objects.create(
                channel_idx=data.channel_idx,
                sku=data.sku,
                parent_sku=product.parent_sku,
                email=email,
                language=data.language.lower(),
                country=data.country.lower(),
                consent_at=timezone.now(),
                consent_text=data.consent_text,
            )
    except IntegrityError:
        return _waiting(data.channel_idx, data.sku, email), False
    row.consent_record_id = consent_bridge.record_grant(row, data.ip_address, data.user_agent)
    if row.consent_record_id is not None:
        row.save(update_fields=["consent_record_id", "modified_at"])
    logger.info("stock alerts: request %s saved", row.pk)
    return row, True


def cancel(subscription: Subscription, reason: CancelReason) -> Subscription:
    """Idempotent: only a waiting row changes."""
    if subscription.status != Status.WAITING:
        return subscription
    subscription.status = Status.CANCELLED
    subscription.cancelled_at = timezone.now()
    subscription.cancel_reason = reason
    subscription.save(update_fields=["status", "cancelled_at", "cancel_reason", "modified_at"])
    if reason in _WITHDRAWING_REASONS and subscription.consent_record_id:
        consent_bridge.record_withdrawal(subscription)
    logger.info("stock alerts: request %s cancelled (%s)", subscription.pk, reason)
    return subscription


def cancel_by_token(channel_idx: str, token: str) -> Subscription:
    """The person's cancel from a link; a token of another channel is a bad token."""
    ensure_channel_open(channel_idx)
    subscription = token_service.read(token)
    if subscription.channel_idx != channel_idx:
        raise token_service.BadToken
    with transaction.atomic():
        locked = Subscription.objects.select_for_update().get(pk=subscription.pk)
        return cancel(locked, CancelReason.USER)
