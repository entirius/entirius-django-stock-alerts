---
title: Concept
description: Why the module works the way it does.
---

## One waiting request per address and variant

A partial unique index on (`channel_idx`, `sku`, `email`) where `status = 'waiting'` is the only guard. `subscribe`
looks the row up first and, when two requests race past the lookup, the loser's insert fails inside a savepoint and
it returns the winner's row: two fast clicks answer 201 twice and store one row. A closed request (`notified`,
`cancelled`, `expired`) never blocks a new one.

The answer is the same for a new and an existing request, and for a honeypot hit, so the API never tells whether an
address already waits.

## Abuse without a captcha

Honeypot field (`website`), a per-client and a per-address throttle (the address only as a digest in the cache
key), a cap of waiting requests per address and channel, and — where access is installed — a publishable channel
key, so anonymous scripts cannot use the route without loading the storefront.

## Two records of one consent

The request keeps when and what exactly the person accepted, always. Where `django_agreements` is installed and the
definition `STOCK_ALERTS_AGREEMENT_SLUG` has a published version, a new request also writes a `ConsentRecord`
(`granted`, source `stock_alerts`, channel, IP, user agent) so the consent shows in the agreements panel under the
person; `consent_record_id` keeps its id (a plain integer, no FK: agreements is optional). A cancel by the person
and a GDPR erasure write the withdrawal; a cancel by an administrator, an undeliverable address or an expiry do not —
the person did not withdraw. A missing definition never blocks a request; `manage.py check` warns.

The definition is `informational`, never marketing, and only `record_consent` is used: newsletter subscriber lists
never pick these addresses up.

## Cancel link

`django.core.signing` with salt `stock-alerts.cancel`; payload = the row's pk and a 16-character digest (keyed with `SECRET_KEY`) of its
address, no max age. An erased row's address is the token, so its old links stop working.

## GDPR

Export finds the person's rows by the plain address or its anonymised token (the platform's
`anon-<sha256[:16]>@<LEADS_ANONYMISED_DOMAIN>`, a local copy pinned to `django_leads` by a test). Erasure first
replaces the address with the token on every row (`anonymised_at` set), then cancels the waiting rows with reason
`erased`: the withdrawal written to agreements already carries the token, whichever app's erase hook runs first.

## Restock check: polling, not signals

Stock reaches the saleable quantity through many paths (imports, orders, cancellations, returns, supplier feeds,
bundles counted from components), and none of them fires one dependable event. The check therefore polls every
5 minutes, but only the SKUs that people wait for: distinct SKUs of `waiting` rows, in batches of
`STOCK_ALERTS_CHECK_BATCH`, through `django_matrix.services.stock_service.get_quantities` — the quantity the cart
accepts. It never walks the catalogue, and its queries do not grow with the number of people waiting.

## Waves

A SKU back with quantity `q` invites `q × STOCK_ALERTS_WAVE_FACTOR` people (factor 0: everyone), oldest request
first. Inviting more people than pieces is deliberate (not everyone buys); inviting everyone for one piece would
disappoint most of them. Each invited row gets `wave_claimed_at` before its send task is enqueued, and a claim
younger than 30 minutes is not taken again: the next check takes the next people in line while the stock lasts.

## Re-check before each send

The send task locks the row, sends nothing unless it is still `waiting`, and reads the quantity again: sold out
in the meantime → the claim is cleared and the row waits for the next restock. A SKU that flaps (back, sold, back)
may get several waves; the re-check bounds the waste. The status check under the lock is the only idempotency
rule: a redelivered (`acks_late`) or concurrent task sends nothing a second time. The email goes out inside the
lock, so a parallel task waits and then sees `notified`.

## Delivery failures

SMTP and socket errors are retried after 2, 10 and 30 minutes; each scheduled retry moves the row's claim past its
run, so no check starts a second retry chain meanwhile. After the last retry the row's `send_attempts`
grows and its claim is cleared, so a later wave tries again; the second such failure closes the row as
`cancelled / undeliverable`. A variant gone from the channel closes it the same way, without a send. Any other
error (no django_email channel for the idx, a broken template) is a configuration fault, not the address's: the task
fails, the row keeps waiting, and the next wave after the claim tries again.

## Retention

Daily: `waiting` rows older than `STOCK_ALERTS_WAITING_DAYS` become `expired`; closed rows (`notified_at`,
`cancelled_at`, or the expiry itself older than `STOCK_ALERTS_ANONYMISE_DAYS`) get the anonymised token instead of
the address. Their cancel links stop working with that, as after an erasure.
