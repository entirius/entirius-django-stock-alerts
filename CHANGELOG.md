# Changelog

## Unreleased

First version: requests, public API, consent, GDPR.

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
- **GDPR** — `gdpr_export`, `gdpr_erase` (address → the platform's anonymised token, waiting rows cancelled).
