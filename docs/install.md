---
title: Install
description: Wiring the module into an Entirius service.
---

## Apps and URLs

```python
INSTALLED_APPS += ["django_stock_alerts"]  # after django_matrix
urlpatterns += [path("", include("django_stock_alerts.urls"))]  # api/stock-alerts/v2/…
```

`python manage.py migrate django_stock_alerts`.

## Settings

All read at import from Django settings of the same name (`src/django_stock_alerts/settings.py`).

| Setting | Default | Meaning |
|---|---|---|
| `STOCK_ALERTS_PRODUCT_URL` | `{}` | per channel idx, a template: `https://shop.example/{country}/product/{url_key}?variant={sku}` |
| `STOCK_ALERTS_CANCEL_URL` | `{}` | per channel idx: `https://shop.example/{country}/stock-alert/cancel?token={token}` |
| `STOCK_ALERTS_WAVE_FACTOR` | `5` | people invited per available piece and wave; `0` = everyone |
| `STOCK_ALERTS_CHECK_BATCH` | `500` | SKUs per quantity query |
| `STOCK_ALERTS_SEND_RATE` | `"120/m"` | Celery rate limit of the send task |
| `STOCK_ALERTS_MAX_WAITING_PER_EMAIL` | `20` | waiting requests per address and channel |
| `STOCK_ALERTS_WAITING_DAYS` | `180` | a request expires after |
| `STOCK_ALERTS_ANONYMISE_DAYS` | `30` | closed rows keep the address this long |
| `STOCK_ALERTS_SIGNUP_EMAIL` | `True` | send the "we will notify you" email |
| `STOCK_ALERTS_AGREEMENT_SLUG` | `"stock-alerts"` | agreement definition of the consent record in `django_agreements`; `None` switches the record off |
| `LEADS_ANONYMISED_DOMAIN` | `"anonymised.invalid"` | domain of the anonymised address token (shared with leads and agreements) |

A channel without `STOCK_ALERTS_PRODUCT_URL` accepts no requests: both public routes answer 404 there.
`manage.py check` errors on a template without `{url_key}` / `{token}` and warns about a channel with waiting
requests and no templates.

## Channel key

With `entirius-django-access` installed the subscribe route needs an `X-API-KEY` with scope
`stock_alerts.subscribe` (publishable: it ships in the storefront bundle). Issue one per channel in the access
panel. **Without access the route is open** to anyone, behind its throttles only. The cancel route never needs a
key: the signed token is the credential.

## Throttles

| Scope (`REST_FRAMEWORK["DEFAULT_THROTTLE_RATES"]`) | Fallback | Counted per |
|---|---|---|
| `stock_alerts_subscribe` | `10/min` | client IP (`CLIENT_IP_HEADER` behind a proxy) |
| `stock_alerts_subscribe_address` | `6/hour` | digest of the e-mail address |
| `stock_alerts_cancel` | `20/min` | client IP |

An unset or malformed rate falls back; it never disables the throttle.

## Agreement fixture

With `entirius-django-agreements` installed, load the definition once:

```bash
python manage.py loaddata stock_alerts_agreement
```

It creates the definition `stock-alerts` (category `informational`, not marketing: newsletter lists never pick
these addresses) with one published version in EN and PL, pk 700 for both rows (check that no other definition or version uses it). A re-load resets both rows; later text changes are
a new version in the agreements panel. Without it (or without a published version) requests are still saved, the
consent stays on the request only, and `manage.py check` warns (`stock_alerts.W003`).

## GDPR

`django_stock_alerts.gdpr` defines `gdpr_export` and `gdpr_erase`, discovered by `django_leads.gdpr.registry`.
