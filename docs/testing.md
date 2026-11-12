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
- `admin/test_demand.py` — aggregation per SKU, only waiting rows, the 30-day notified window, quantity (missing = 0),
  default and allowed orderings, search by SKU prefix and name, pagination, bad ordering 400, query count independent
  of the page size, other channels left out.
- `admin/test_subscriptions.py` — row shape, each filter, exact-address search (no substring), ordering, bad ordering
  400, other channels never shown; cancel: waiting → `admin`, closed row unchanged, other channel 404.
- `admin/test_export.py` — header, filters, formula guard, the token of an anonymised row.
- `admin/test_auth.py` — 401 without a token, 403 for non-staff; with access: 403 without the area, read-only staff
  read but cannot cancel (the gate middleware is on in `tests/settings.py` when access is importable).
- `test_access_ownership.py` — every admin route covered by the module's own access declarations.
- `test_migrations.py` — no model change without a migration.
