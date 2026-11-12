---
title: Operations
description: Reading the log lines, re-running a wave, what the final states mean.
---

## Log lines

| Line | Meaning |
|---|---|
| `event=stock_alerts.check channels=<idx,…> skus=N back=B enqueued=E` | one check: N SKUs with waiting rows read, B of them saleable, E alerts enqueued |
| `event=stock_alerts.check skipped=locked` | another check still runs (or crashed less than 4 minutes ago) |
| `event=stock_alerts.retention expired=X anonymised=Y` | the daily retention |
| `stock alerts: request <pk> notified` | one alert sent |
| `stock alerts: request <pk> alert delivery failed (attempt n)` | all retries of one send failed |

Addresses are never logged, only row pks. `back` > 0 with `enqueued=0` means every waiting row of those SKUs is
claimed by a wave younger than 30 minutes.

`channels=-` means no channel has both `STOCK_ALERTS_PRODUCT_URL` and `STOCK_ALERTS_CANCEL_URL`.

## Running by hand

```bash
python manage.py shell -c "from django_stock_alerts.tasks import check; check.delay()"
python manage.py shell -c "from django_stock_alerts.tasks import retention; retention.delay()"
```

## Re-running a wave

A wave's rows stay claimed for 30 minutes. To send a wave again sooner (after fixing SMTP, say), clear the claim of
the SKU's waiting rows and run the check:

```bash
python manage.py shell -c "from django_stock_alerts.models import Subscription; Subscription.objects.filter(channel_idx='<idx>', sku='<sku>', status='waiting').update(wave_claimed_at=None)"
```

Rows already `notified` are never sent again.

## Final states

| Status / reason | Means |
|---|---|
| `notified` | the alert went out once |
| `cancelled / user` | the person used the cancel link |
| `cancelled / undeliverable` | two alert deliveries failed after all retries, or the variant is gone from the channel |
| `cancelled / erased` | GDPR erasure |
| `expired` | waited longer than `STOCK_ALERTS_WAITING_DAYS` |

A configuration fault (no django_email channel with the matrix channel's idx, a missing template) fails the send task
in the worker log and leaves the row `waiting`; every wave retries it until the fault is fixed. It never closes the
request.

The alert's price is the channel's default currency, the row of the request's country when matrix has one.

A worker must consume `stock_alerts`; without it the check enqueues alerts that wait in the broker and are sent
when a worker starts (each re-checks the stock first).
