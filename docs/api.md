---
title: Public API
description: The storefront routes of back-in-stock alerts.
---

Errors use the v2 format (`error`, `message`, `debug_id`, `details`).

## Save a request

`POST api/stock-alerts/v2/<channel_idx>/subscriptions/` — header `X-API-KEY` (scope `stock_alerts.subscribe`) where
access is installed.

```json
{"email": "anna@example.com", "sku": "TSHIRT-RED-M", "language": "en", "country": "pl",
 "consent": true, "consent_text": "Email me when it is back.", "website": ""}
```

| Field | Rule |
|---|---|
| `email` | valid address, ≤ 254 characters; compared and stored lower-cased |
| `sku` | the sold-out variant, ≤ 255 characters |
| `language` | two letters |
| `country` | two letters or empty (the storefront country segment of the links) |
| `consent` | must be `true` |
| `consent_text` | the exact text shown, 1–2000 characters |
| `website` | honeypot: leave empty |

| Answer | When |
|---|---|
| `201 {"status": "saved"}` | a new request, an existing waiting one, or a filled honeypot (nothing stored) — the same bytes |
| `400 VALIDATION_ERROR` | body invalid |
| `401` / `403` | no key / a key not valid for this scope and channel (access installed) |
| `404 NOT_FOUND` | unknown SKU of the channel, a configurable parent (wait for one of its variants), or a channel without URL templates |
| `409 IN_STOCK` | the variant can be bought now |
| `429 RATE_LIMITED` | throttled per client or per address |
| `429 TOO_MANY_REQUESTS` | the address waits for `STOCK_ALERTS_MAX_WAITING_PER_EMAIL` variants in the channel |

## Cancel a request

`POST api/stock-alerts/v2/<channel_idx>/subscriptions/cancel/` body `{"token": "…"}` — no key.

| Answer | When |
|---|---|
| `200 {"status": "cancelled"}` | cancelled now, or already closed |
| `400 INVALID_REQUEST` | bad signature, unknown request, a token of another channel, or a request whose address was erased |
| `404` | channel without URL templates |
| `429 RATE_LIMITED` | throttled per client |
