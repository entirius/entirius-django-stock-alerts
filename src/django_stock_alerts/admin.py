# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

from django.contrib import admin

from django_stock_alerts.models import Subscription


@admin.register(Subscription)
class SubscriptionAdmin(admin.ModelAdmin):
    """Read only: every change goes through `subscription_service` (cancel writes the withdrawal, the index guards)."""

    list_display = ("id", "channel_idx", "sku", "status", "cancel_reason", "created_at", "notified_at")
    list_filter = ("status", "channel_idx", "cancel_reason")
    search_fields = ("sku", "parent_sku")
    ordering = ("-created_at",)

    def has_add_permission(self, request) -> bool:
        return False

    def has_change_permission(self, request, obj=None) -> bool:
        return False
