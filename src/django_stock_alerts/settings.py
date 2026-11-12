# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Module settings, read at import: a host sets a Django setting of the same name (table in `docs/install.md`)."""

from django.conf import settings

# Per channel idx, the storefront product link: "https://shop.example/{country}/product/{url_key}?variant={sku}".
# A channel without one accepts no requests: the public API answers 404 there.
PRODUCT_URL: dict[str, str] = getattr(settings, "STOCK_ALERTS_PRODUCT_URL", {})
# Per channel idx, the cancel link: "https://shop.example/{country}/stock-alert/cancel?token={token}".
CANCEL_URL: dict[str, str] = getattr(settings, "STOCK_ALERTS_CANCEL_URL", {})
# People invited per available piece and wave; 0 = everyone.
WAVE_FACTOR: int = getattr(settings, "STOCK_ALERTS_WAVE_FACTOR", 5)
# SKUs per quantity query of the restock check.
CHECK_BATCH: int = getattr(settings, "STOCK_ALERTS_CHECK_BATCH", 500)
# Celery rate limit of the send task.
SEND_RATE: str = getattr(settings, "STOCK_ALERTS_SEND_RATE", "120/m")
# Waiting requests per address and channel.
MAX_WAITING_PER_EMAIL: int = getattr(settings, "STOCK_ALERTS_MAX_WAITING_PER_EMAIL", 20)
# A waiting request expires after this many days.
WAITING_DAYS: int = getattr(settings, "STOCK_ALERTS_WAITING_DAYS", 180)
# Closed requests keep the address this many days.
ANONYMISE_DAYS: int = getattr(settings, "STOCK_ALERTS_ANONYMISE_DAYS", 30)
# Send the "we will notify you" email.
SIGNUP_EMAIL: bool = getattr(settings, "STOCK_ALERTS_SIGNUP_EMAIL", True)
# Agreement definition the consent is recorded against in django_agreements; None switches the record off.
AGREEMENT_SLUG: str | None = getattr(settings, "STOCK_ALERTS_AGREEMENT_SLUG", "stock-alerts")
# Domain of the anonymised address token; the same setting django_leads and django_agreements read.
ANONYMISED_DOMAIN: str = getattr(settings, "LEADS_ANONYMISED_DOMAIN", "anonymised.invalid")
