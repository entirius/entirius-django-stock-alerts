# AGENTS.md

entirius-django-stock-alerts (Django app `django_stock_alerts`) — back-in-stock alerts of Entirius: a storefront
saves a request for a sold-out variant, the person is emailed once when it can be bought again. Table prefix
`django_stock_alerts_`.

## Commands

| Command | Meaning |
|---|---|
| `make install` | `uv sync --all-extras` (run once before `check`) |
| `make test` | pytest — PostgreSQL only: `DATABASE_URL`, else the default in `tests/settings.py` (`docs/testing.md`) |
| `make check` / `fix` | ruff lint + format (+ canonical `.gitleaks.toml` guard) |

## Conventions

- English only; MPL-2.0 header on every `.py` (`insert-license`); no Claude attribution trailers in commits or PRs.
- Layered: `models/` · `services/` · `schemas/` · `api/public/`. No logic in models, no ORM in views.
- Never rename the package, the app label or the table prefix; never edit a released migration.
- Soft dependencies `django_access` and `django_agreements`: imported lazily, never at module import time, no FK.
  The suite runs with agreements and without (`STOCK_ALERTS_TEST_NO_AGREEMENTS=1`).
- Never log an address: log the row pk.
- Access: areas and token scopes live on the AppConfig; every admin view carries `access_area`
  (`tests/test_access_ownership.py`).
- Git flow: `develop` + `master`, PRs. Do not commit by default — the operator decides.

## Architecture

Read first: `docs/install.md` (host) · `docs/api.md` (caller) · `docs/concept.md` (why).

```
src/django_stock_alerts/
├── apps.py (access areas, token scope)  enums.py  settings.py (read at import)  checks.py  gdpr.py  admin.py  urls.py
├── models/        subscription.py (partial unique index: one waiting row per channel, sku, email)
├── schemas/       requests.py  responses.py
├── services/      subscription_service (subscribe, cancel: the only writer)  token_service (signed cancel link)
│                  catalog (the only reader of django_matrix)  consent_bridge (the only importer of django_agreements)
├── api/public/    views.py  throttling.py  authentication.py (channel key)  urls.py
└── fixtures/      stock_alerts_agreement.json (agreement definition, loaded once by a host)
```

| Topic | Where |
|---|---|
| A setting's name, default, meaning | `settings.py`; the table in `docs/install.md` |
| Host wiring: apps, URLs, key, throttles, agreement fixture | `docs/install.md` |
| Request / response shape, errors | `docs/api.md`; `schemas/` |
| Consent records, uniqueness, GDPR — why | `docs/concept.md` |
| Which test file covers what | `docs/testing.md` |
| What changed and why | `CHANGELOG.md` |

## Gotchas

- The partial unique index is the only uniqueness guard: `subscribe` catches `IntegrityError` in a savepoint and
  re-reads; a second guard elsewhere would drift.
- `get_quantities` leaves out SKUs without stock data: a missing key is 0.
- Throttles keep their fallback in `fallback_rate`, never in a class `rate` (DRF skips `get_rate()` then).
- Settings are read at import: tests patch `django_stock_alerts.settings` attributes, not Django settings.
- `consent_bridge` uses `record_consent` only, against a non-marketing definition: newsletter lists never see
  these addresses.
