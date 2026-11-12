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
