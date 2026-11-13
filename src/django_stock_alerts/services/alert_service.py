# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Sends the alert and the signup email of one request; the only writer of `notified` and of the wave claim's end.

The status check under the row lock is the idempotency rule: a redelivered or concurrent task for a row that is no
longer `waiting` sends nothing. The email goes out inside that lock, so a second task waits and then sees `notified`.
"""

import logging
from datetime import timedelta
from smtplib import SMTPException

from django.db import transaction
from django.utils import timezone, translation
from django_email.dto import StockAlertData
from django_email.service.stock_alerts.available import StockAlertAvailableEmail
from django_email.service.stock_alerts.signup import StockAlertSignupEmail
from django_email.urls_helper import absolute_media_url

from django_stock_alerts.enums import CancelReason, Status
from django_stock_alerts.models import Subscription
from django_stock_alerts.services import catalog, subscription_service

logger = logging.getLogger(__name__)

# Transient transport errors: the task retries these.
RETRYABLE_ERRORS = (SMTPException, OSError)
# Failed alert deliveries (each after its retries) before the request is closed as undeliverable.
MAX_SEND_ATTEMPTS = 2


def send_alert(subscription_id: int) -> str:
    """`notified`, or why not: `skipped` (not waiting), `sold_out` (claim cleared), `undeliverable` (product gone)."""
    with transaction.atomic():
        row = Subscription.objects.select_for_update().filter(pk=subscription_id).first()
        if row is None or row.status != Status.WAITING:
            return "skipped"
        if catalog.saleable_quantity(row.channel_idx, row.sku) < 1:
            _release_claim(row)
            return "sold_out"
        card = catalog.describe(row.channel_idx, row.sku, row.language, row.country)
        if card is None:
            subscription_service.cancel(row, CancelReason.UNDELIVERABLE)
            return "undeliverable"
        _send(StockAlertAvailableEmail, row, card)
        _mark_notified(row)
    return "notified"


def record_failed_delivery(subscription_id: int) -> None:
    """After the last retry: the row waits for the next wave, or closes as undeliverable after `MAX_SEND_ATTEMPTS`."""
    with transaction.atomic():
        row = Subscription.objects.select_for_update().filter(pk=subscription_id).first()
        if row is None or row.status != Status.WAITING:
            return
        row.send_attempts += 1
        _release_claim(row)
        if row.send_attempts >= MAX_SEND_ATTEMPTS:
            subscription_service.cancel(row, CancelReason.UNDELIVERABLE)
    logger.warning("stock alerts: request %s alert delivery failed (attempt %s)", row.pk, row.send_attempts)


def hold_claim(subscription_id: int, seconds: int) -> None:
    """Move the wave claim `seconds` ahead (a scheduled retry), so the check does not start a second retry chain."""
    claimed_until = timezone.now() + timedelta(seconds=seconds)
    Subscription.objects.filter(pk=subscription_id, status=Status.WAITING).update(wave_claimed_at=claimed_until)


def send_signup(subscription_id: int) -> None:
    """The "we will notify you" email of a waiting request; it never changes the row."""
    row = Subscription.objects.filter(pk=subscription_id, status=Status.WAITING).first()
    card = row and catalog.describe(row.channel_idx, row.sku, row.language, row.country)
    if card:
        _send(StockAlertSignupEmail, row, card)


def _send(service_class: type, row: Subscription, card: catalog.ProductCard) -> None:
    # EmailService activates its language globally: one service per send, the worker's language restored after.
    with translation.override(row.language):
        service = service_class(language=row.language, channel_idx=row.channel_idx)
        service.send(email=[row.email], data=_email_data(row, card))


def _email_data(row: Subscription, card: catalog.ProductCard) -> StockAlertData:
    return StockAlertData(
        product_name=card.name,
        variant_line=card.variant_line,
        image_url=absolute_media_url(card.image_path) if card.image_path else None,
        price=card.price,
        currency=card.currency,
        product_url=catalog.product_url(row, card.url_key),
        cancel_url=catalog.cancel_url(row),
    )


def _release_claim(row: Subscription) -> None:
    row.wave_claimed_at = None
    row.save(update_fields=["wave_claimed_at", "send_attempts", "modified_at"])


def _mark_notified(row: Subscription) -> None:
    row.status = Status.NOTIFIED
    row.notified_at = timezone.now()
    row.wave_claimed_at = None
    row.save(update_fields=["status", "notified_at", "wave_claimed_at", "modified_at"])
    logger.info("stock alerts: request %s notified", row.pk)
