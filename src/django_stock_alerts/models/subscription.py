# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

from django.db import models
from django_utils.models.base_model import BaseModel

from django_stock_alerts.enums import CancelReason, Status


class Subscription(BaseModel):
    """One person waiting for one variant in one channel. Rules live in `services/subscription_service.py`."""

    channel_idx = models.CharField(max_length=64, db_index=True)
    sku = models.CharField(max_length=255, help_text="The variant the person waits for")
    parent_sku = models.CharField(max_length=255, blank=True, default="", help_text="Configurable parent")
    email = models.EmailField(max_length=254, help_text="Lower-cased; the anonymised token after erasure")
    language = models.CharField(max_length=2)
    country = models.CharField(max_length=2, blank=True, default="", help_text="Storefront country segment")
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.WAITING)
    consent_at = models.DateTimeField()
    consent_text = models.TextField(help_text="The exact text the person accepted")
    consent_record_id = models.PositiveBigIntegerField(
        null=True, blank=True, help_text="ConsentRecord in django_agreements, when installed (no FK on purpose)"
    )
    notified_at = models.DateTimeField(null=True, blank=True)
    cancelled_at = models.DateTimeField(null=True, blank=True)
    cancel_reason = models.CharField(max_length=16, choices=CancelReason.choices, blank=True, default="")
    send_attempts = models.PositiveSmallIntegerField(default=0, help_text="Failed deliveries of the alert")
    anonymised_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["channel_idx", "sku", "email"],
                condition=models.Q(status=Status.WAITING),
                name="django_stock_alerts_one_waiting",
            )
        ]
        indexes = [
            models.Index(fields=["status", "channel_idx", "sku", "created_at"], name="django_stock_alerts_status"),
        ]

    def __str__(self) -> str:
        return f"{self.channel_idx}:{self.sku} #{self.pk} ({self.status})"
