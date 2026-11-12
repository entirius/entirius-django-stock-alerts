# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

from django.apps import AppConfig

SUBSCRIBE_SCOPE = "stock_alerts.subscribe"


class DjangoStockAlertsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "django_stock_alerts"
    label = "django_stock_alerts"
    verbose_name = "Back-in-stock alerts"
    is_volkanos = True
    # The admin API (a later release) carries this area on every view; no route needs a path rule.
    access_areas = [
        {"key": "stock_alerts.subscriptions", "label": "Back-in-stock requests", "sensitive": ("pii",)},
    ]
    access_token_scopes = [
        {
            "key": SUBSCRIBE_SCOPE,
            "label": "Back-in-stock requests",
            "publishable": True,
            "routes": ("/api/stock-alerts/v2/{channel_idx}/subscriptions/",),
        },
    ]
    access_route_rules = []

    def ready(self) -> None:
        import django_stock_alerts.checks  # noqa: F401 — registers the configuration checks
