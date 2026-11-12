# Changelog

## Unreleased

First version: requests, public API, consent, GDPR, restock check, alert and signup emails, retention.

- **`Subscription`** — one person waiting for one variant in one channel: status `waiting` · `notified` ·
  `cancelled` · `expired`, consent time and text, the agreements `consent_record_id`. A partial unique index keeps
  one waiting row per channel, SKU and address.
- **`subscription_service`** — `subscribe` (product must exist and be sold out, cap per address, race-safe
  `get_or_create`), `cancel` (idempotent; a withdrawal in agreements when the person or an erasure ends it),
  `cancel_by_token`.
- **Public API** — `POST api/stock-alerts/v2/<channel_idx>/subscriptions/` and `…/subscriptions/cancel/`: honeypot,
  throttles with fallback rates, channel key scope `stock_alerts.subscribe` where access is installed, 404 for a
  channel without URL templates.
- **Consent in agreements** — fixture `stock_alerts_agreement` (definition `stock-alerts`, informational); grant on
  a new request, withdrawal on the person's cancel or erasure.
- **Checks** — templates without their placeholder (error), waiting channels without templates and an unpublished
  agreement (warnings).
- **Admin API** — `api/stock-alerts/v2/admin/<channel_idx>/`: `demand/` (waiting requests per variant with the
  stock now and the notified count of 30 days), `subscriptions/` (filters, exact-address search), `subscriptions/export/`
  (streamed CSV, formula guard), `subscriptions/<id>/cancel/` (reason `admin`); JWT, `IsAdminUser`, area
  `stock_alerts.subscriptions`; orderings by allowlist.
- **GDPR** — `gdpr_export`, `gdpr_erase` (address → the platform's anonymised token, waiting rows cancelled).
- **Restock check** — task `django_stock_alerts.check` (beat, every 5 min, queue `stock_alerts`, cache lock): reads
  quantities of waited-for SKUs only, enqueues a wave of `quantity × STOCK_ALERTS_WAVE_FACTOR` oldest requests; field
  `wave_claimed_at` (migration `0002`) keeps a wave from being taken twice within 30 minutes.
- **Alert** — task `django_stock_alerts.send_alert` (`acks_late`, rate limit `STOCK_ALERTS_SEND_RATE`): row lock,
  stock re-check, `StockAlertAvailableEmail` from `entirius-django-email`, `notified`; retries after 2, 10, 30 min;
  two exhausted deliveries or a product gone → `cancelled / undeliverable`.
- **Signup email** — task `django_stock_alerts.send_signup` after a new request (`STOCK_ALERTS_SIGNUP_EMAIL`).
- **`catalog.describe`** — name, variant line, picture, URL key and price of a variant in a language; `product_url`,
  `cancel_url` from the channel templates.
- **Retention** — task `django_stock_alerts.retention` (daily): expiry after `STOCK_ALERTS_WAITING_DAYS`,
  anonymisation of closed rows after `STOCK_ALERTS_ANONYMISE_DAYS`.
- New dependencies: `entirius-django-email` (the floor moves to the email release that ships the stock-alert
  emails), `celery`.
