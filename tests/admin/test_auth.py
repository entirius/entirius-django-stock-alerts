# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
"""JWT + `IsAdminUser` on every admin route; with django_access the gate also asks for the area."""

import pytest
from rest_framework.test import APIClient

from django_stock_alerts.enums import Status
from tests.admin.conftest import admin_url, make_row
from tests.conftest import WITH_ACCESS

pytestmark = pytest.mark.django_db

READS = [admin_url("demand/"), admin_url("subscriptions/"), admin_url("subscriptions/export/")]
needs_access = pytest.mark.skipif(not WITH_ACCESS, reason="django_access is not installed")


@pytest.mark.parametrize("url", READS)
def test_without_a_token_is_401(url):
    assert APIClient().get(url).status_code == 401


def test_cancel_without_a_token_is_401():
    assert APIClient().post(admin_url("subscriptions/1/cancel/")).status_code == 401


@pytest.mark.parametrize("url", READS)
def test_not_staff_is_403(make_client, url):
    assert make_client(is_staff=False).get(url).status_code == 403


@needs_access
@pytest.mark.parametrize("url", READS)
def test_staff_without_the_area_is_403(make_client, url):
    assert make_client().get(url).status_code == 403


@needs_access
@pytest.mark.parametrize("url", READS)
def test_read_only_staff_reads(viewer, products, quantities, url):
    assert viewer.get(url).status_code == 200


@needs_access
def test_read_only_staff_cannot_cancel(viewer, products):
    row = make_row()
    assert viewer.post(admin_url(f"subscriptions/{row.pk}/cancel/")).status_code == 403
    row.refresh_from_db()
    assert row.status == Status.WAITING
