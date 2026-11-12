---
title: Test suite map
description: Which test file covers what.
---

Postgres only (`tests/settings.py`): `DATABASE_URL`, else
`postgresql://postgres:postgres@localhost:5432/test_stock_alerts`. Matrix is installed (hard requirement); the tests
build its rows directly and patch `get_quantities`, so they never need checkout. The suite runs twice:

```bash
make test                                       # with django_agreements
STOCK_ALERTS_TEST_NO_AGREEMENTS=1 make test     # without it
```

In the entirius-zeno harness: `make module-test MODULE=entirius-django-stock-alerts` (django_access installed too).

- `test_subscription_service.py` — consent time and text stored; same request → same row, any case of the address;
  second SKU → second row; in stock, unknown SKU, a configurable parent, closed channel, cap; re-subscribe after `notified` / `cancelled`;
  cancel idempotent; two concurrent subscribes → one row, two answers.
- `test_public_api.py` — byte-identical 201 for new and existing; 409 `IN_STOCK`; 404; 429 `TOO_MANY_REQUESTS`;
  400 for consent false or missing, bad e-mail, language, empty text; honeypot; channel without templates;
  cancel with a valid, repeated, tampered, other-channel and anonymised-row token; a forwarded IP list stored as no IP.
- `test_access_keys.py` — without a key 401, a key of another scope 403, the key 201; cancel needs none.
- `test_throttling.py` — each scope limits; unset, malformed, empty and `None` rates fall back.
- `test_consent_bridge.py` — one grant per new request with its fields and id; withdrawal on the person's cancel and
  erasure, none on admin or undeliverable; never a marketing subscriber; missing or unpublished definition and slug
  `None` → request saved without a record; without the app.
- `test_gdpr.py` — export by address and by token; erase cancels waiting rows and anonymises all; the withdrawal
  carries the token; parity of the token with `django_leads`.
- `test_checks.py` — templates without their placeholder, waiting channel without templates, unpublished agreement.
- `test_openapi.py` — `spectacular --validate --fail-on-warn`.
- `test_access_ownership.py` — every admin route covered by the module's own access declarations.
- `test_catalog.py` — the email card in a language (parent name, variant line, picture ≥ 240 px, price of the
  channel currency and the request's country), multiselect values, fallbacks without data, product gone, bounded queries; URL builders: quoting, no `{country}`.
- `test_check.py` — no waiting rows → no quantity query; sold out → nothing; quantity × factor oldest first, the next
  run skips claimed rows; stale claim; factor 0; channel without templates; batches; lock; log line; queries
  independent of the number of people.
- `test_send.py` — alert sent once and `notified`; already notified; sold out again (claim cleared); product gone;
  SMTP retry and countdowns; a scheduled retry holds the claim; retries exhausted twice → `undeliverable`; two
  concurrent tasks → one message; a configuration error keeps the row waiting.
- `test_signup_email.py` — created request → one signup email; repeated request → none; setting off; a failed send
  leaves the row.
- `test_retention.py` — expiry at the boundary and in batches; anonymisation of closed rows past the period only.
- `test_migrations.py` — no model change without a migration.
