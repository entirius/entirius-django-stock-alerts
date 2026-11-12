---
title: Back-in-stock alerts
description: What the module does and where its documents are.
---

A person on a sold-out variant leaves an address and a consent; the module keeps one waiting request per address
and variant, and emails the person once when the variant can be bought again: a restock check every 5 minutes sends
alerts in waves sized to the available quantity, and a daily retention expires old requests and anonymises closed
ones.

| Document | For |
|---|---|
| [`install.md`](install.md) | host: apps, URLs, settings, the channel key, the agreement fixture |
| [`api.md`](api.md) | storefront: the public routes, bodies, answers |
| [`concept.md`](concept.md) | why: uniqueness, consent records, abuse defences, GDPR, polling, waves, retention |
| [`operations.md`](operations.md) | operator: log lines, running and re-running, final states |
| [`testing.md`](testing.md) | which test covers what |
| [`erd-config.yaml`](erd-config.yaml) | ERD groups |
