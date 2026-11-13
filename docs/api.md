---
title: API
description: The storefront and admin routes of back-in-stock alerts.
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

## Admin API

JWT (`Authorization: Bearer …`), staff only (`IsAdminUser`), access area `stock_alerts.subscriptions` (marked `pii`):
read for the `GET` routes, write for cancel. Routes under `api/stock-alerts/v2/admin/<channel_idx>/`. Lists are
paginated (`page`, `page_size` ≤ 100, default 20) and answer `{count, next, previous, results}`.

| Answer | When |
|---|---|
| `400 VALIDATION_ERROR` | an `ordering` or `status` outside the allowlist |
| `401` / `403` | no token / not staff, or no permission on the area |
| `404 NOT_FOUND` | cancel of an unknown request or a request of another channel |

### Demand

`GET demand/?search=&ordering=` — one row per variant with waiting requests; the response also carries
`total_waiting` (requests waiting across the matching variants).

```json
{"sku": "TSHIRT-RED-M", "parent_sku": "TSHIRT", "product_name": "Red T-shirt", "variant_line": "Size: M",
 "waiting": 4, "oldest_request": "2026-11-02T09:12:00Z", "quantity": 0, "notified_30d": 2}
```

`product_name` and `variant_line` come from the catalogue in the channel's default language (`null` when the SKU is
gone); `quantity` is the saleable quantity now. `search`: SKU prefix or part of the product name. `ordering`:
`-waiting` (default), `waiting`, `oldest_request`, `-oldest_request`, `sku`.

### Requests

`GET subscriptions/?status=&sku=&search=&ordering=&page=`

```json
{"id": 7, "sku": "TSHIRT-RED-M", "product_name": "Red T-shirt", "variant_line": "Size: M",
 "email": "anna@example.com", "language": "en", "status": "waiting", "created": "2026-11-02T09:12:00Z",
 "notified_at": null, "cancelled_at": null, "cancel_reason": ""}
```

`search`: the exact address (any case) or a SKU prefix — never a substring of an address. `ordering`: `-created`
(default), `created`, `notified_at`, `-notified_at`. An anonymised row shows its token as `email`.

### Export

`GET subscriptions/export/?status=&sku=&search=` — CSV of the filtered requests, newest first, streamed:
`sku, product_name, variant_line, email, language, status, created, notified_at`. A cell starting with `=`, `+`,
`-`, `@`, a tab or a carriage return is prefixed with `'`.

### Cancel

`POST subscriptions/<id>/cancel/` → the row; reason `admin` (no withdrawal in agreements). A request that is no
longer waiting comes back unchanged.
