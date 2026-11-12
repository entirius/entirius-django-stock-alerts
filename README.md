# entirius-django-stock-alerts

Back-in-stock alerts for [Entirius](https://docs.entirius.com/): a storefront saves a request for a sold-out
variant ("email me when it is back"), with the consent the person gave, and cancels it from a signed email link.

- One waiting request per address and variant; repeated requests answer the same, so nobody learns whether an
  address had one.
- Bots and floods kept out without a captcha: honeypot field, per-client and per-address throttles, a cap of
  waiting requests per address.
- Consent stored on the request (time and exact text) and, where `entirius-django-agreements` is installed, as a
  consent record in the agreements panel.
- GDPR hooks: export and erasure of a person's requests.

Requires `entirius-django-matrix` (catalogue and saleable quantity) and `entirius-django-utils`. Optional:
`entirius-django-access` (channel key on the subscribe route), `entirius-django-agreements` (consent records).

## Install

```bash
uv add entirius-django-stock-alerts
```

Wiring, settings and the agreement fixture: [`docs/install.md`](docs/install.md). API: [`docs/api.md`](docs/api.md).

## Development

```bash
make install
make check
make test   # PostgreSQL: DATABASE_URL, see docs/testing.md
```

## License

[MPL-2.0](LICENSE)
