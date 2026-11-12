# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
from datetime import timedelta

from django.utils import timezone

from django_stock_alerts import settings as stock_settings
from django_stock_alerts.enums import Status
from django_stock_alerts.gdpr import anonymised_address
from django_stock_alerts.models import Subscription
from django_stock_alerts.services import retention_service
from django_stock_alerts.tasks.retention import retention

from .conftest import make_row

DAY = timedelta(days=1)
MINUTE = timedelta(minutes=1)


def aged(row: Subscription, **times) -> Subscription:
    Subscription.objects.filter(pk=row.pk).update(**times)
    row.refresh_from_db()
    return row


def test_waiting_expires_at_the_boundary(db, caplog):
    edge = timezone.now() - stock_settings.WAITING_DAYS * DAY
    old = aged(make_row(email="old@example.com"), created_at=edge - MINUTE)
    young = aged(make_row(email="young@example.com"), created_at=edge + MINUTE)

    with caplog.at_level("INFO", logger="django_stock_alerts.tasks.retention"):
        assert retention() == {"expired": 1, "anonymised": 0}

    old.refresh_from_db(), young.refresh_from_db()
    assert (old.status, young.status) == (Status.EXPIRED, Status.WAITING)
    assert old.email == "old@example.com"  # anonymised only after the closed period
    assert "event=stock_alerts.retention expired=1 anonymised=0" in caplog.text


def test_anonymises_only_closed_rows_past_the_period(db):
    edge = timezone.now() - stock_settings.ANONYMISE_DAYS * DAY
    past = {"notified_at": edge - MINUTE}
    notified = aged(make_row(email="n@example.com", status=Status.NOTIFIED), **past)
    cancelled = aged(make_row(email="c@example.com", status=Status.CANCELLED), cancelled_at=edge - MINUTE)
    expired = aged(make_row(email="e@example.com", status=Status.EXPIRED), modified_at=edge - MINUTE)
    recent = aged(make_row(email="r@example.com", status=Status.NOTIFIED), notified_at=edge + MINUTE)
    old_waiting = aged(make_row(email="w@example.com"), created_at=edge - MINUTE)

    assert retention_service.run_retention().anonymised == 3

    for row, email in ((notified, "n@"), (cancelled, "c@"), (expired, "e@")):
        row.refresh_from_db()
        assert row.email == anonymised_address(f"{email}example.com")
        assert row.anonymised_at is not None
    recent.refresh_from_db(), old_waiting.refresh_from_db()
    assert recent.email == "r@example.com" and recent.anonymised_at is None
    assert old_waiting.email == "w@example.com"


def test_anonymised_rows_are_not_touched_again(db, monkeypatch):
    monkeypatch.setattr(retention_service, "BATCH", 2)
    edge = timezone.now() - stock_settings.ANONYMISE_DAYS * DAY
    for i in range(5):
        aged(make_row(email=f"p{i}@example.com", status=Status.NOTIFIED), notified_at=edge - MINUTE)

    assert retention_service.run_retention().anonymised == 5
    assert retention_service.run_retention().anonymised == 0


def test_expiry_runs_in_batches(db, monkeypatch):
    monkeypatch.setattr(retention_service, "BATCH", 2)
    edge = timezone.now() - stock_settings.WAITING_DAYS * DAY
    for i in range(5):
        aged(make_row(email=f"w{i}@example.com"), created_at=edge - MINUTE)

    assert retention_service.run_retention().expired == 5
    assert Subscription.objects.filter(status=Status.EXPIRED).count() == 5
