# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
from datetime import timedelta

import pytest
from django.db import connection
from django.test.utils import CaptureQueriesContext
from django.utils import timezone

from django_stock_alerts.enums import Status
from tests.admin.conftest import admin_url, make_row
from tests.conftest import SKU, SKU_2

pytestmark = pytest.mark.django_db

DEMAND = admin_url("demand/")


def _results(client, **params) -> list[dict]:
    response = client.get(DEMAND, params)
    assert response.status_code == 200, response.content
    return response.json()["results"]


def test_aggregates_waiting_rows_per_sku(staff, catalogue, quantities):
    old = make_row(email="a@example.com")
    make_row(email="b@example.com")
    make_row(sku=SKU_2, email="c@example.com")
    make_row(email="d@example.com", status=Status.CANCELLED)
    old.created_at = timezone.now() - timedelta(days=3)
    old.save(update_fields=["created_at"])
    response = staff.get(DEMAND)
    body = response.json()
    assert (body["count"], body["total_waiting"]) == (2, 3)
    first = body["results"][0]
    assert (first["sku"], first["waiting"], first["parent_sku"]) == (SKU, 2, "TSHIRT")
    assert first["oldest_request"].startswith(old.created_at.date().isoformat())
    assert (first["product_name"], first["variant_line"]) == ("Red T-shirt", "Size: M")


def test_only_waiting_rows_make_a_row(staff, catalogue, quantities):
    make_row(status=Status.NOTIFIED, notified_at=timezone.now())
    make_row(sku=SKU_2, status=Status.EXPIRED)
    assert _results(staff) == []


def test_notified_in_the_last_30_days(staff, catalogue, quantities):
    make_row()
    make_row(email="new@example.com", status=Status.NOTIFIED, notified_at=timezone.now() - timedelta(days=29))
    make_row(email="old@example.com", status=Status.NOTIFIED, notified_at=timezone.now() - timedelta(days=31))
    assert _results(staff)[0]["notified_30d"] == 1


def test_quantity_now_and_missing_stock_data_is_zero(staff, catalogue, quantities):
    quantities[SKU] = 3
    make_row()
    make_row(sku=SKU_2)
    by_sku = {row["sku"]: row["quantity"] for row in _results(staff)}
    assert by_sku == {SKU: 3, SKU_2: 0}


def test_default_order_is_most_waiting_first(staff, catalogue, quantities):
    make_row(sku=SKU_2)
    make_row(sku=SKU_2, email="b@example.com")
    make_row()
    assert [row["sku"] for row in _results(staff)] == [SKU_2, SKU]
    assert [row["sku"] for row in _results(staff, ordering="waiting")] == [SKU, SKU_2]
    assert [row["sku"] for row in _results(staff, ordering="sku")] == sorted([SKU, SKU_2])


def test_search_by_sku_prefix_and_by_name(staff, catalogue, quantities):
    make_row()
    make_row(sku="OTHER-1")
    assert [row["sku"] for row in _results(staff, search="OTH")] == ["OTHER-1"]
    assert [row["sku"] for row in _results(staff, search="red t-sh")] == [SKU]


def test_pagination(staff, catalogue, quantities):
    for index in range(3):
        make_row(sku=f"SKU-{index}")
    body = staff.get(DEMAND, {"page_size": 2, "page": 2}).json()
    assert (body["count"], len(body["results"]), body["next"]) == (3, 1, None)


@pytest.mark.parametrize("ordering", ["email", "created_at", "-pk", "waiting;drop"])
def test_bad_ordering_is_400(staff, ordering):
    assert staff.get(DEMAND, {"ordering": ordering}).status_code == 400


def test_query_count_does_not_grow_with_the_page(staff, catalogue, quantities):
    for index in range(6):
        make_row(sku=f"SKU-{index}")
    make_row()
    make_row(email="b@example.com")  # the catalogued SKU leads page 1: every prefetch runs for any page size
    staff.get(DEMAND)  # warm the per-user caches of auth and the gate

    def queries(page_size: int) -> int:
        with CaptureQueriesContext(connection) as captured:
            assert staff.get(DEMAND, {"page_size": page_size}).status_code == 200
        return len(captured)

    assert queries(1) == queries(7)


def test_another_channel_is_not_counted(staff, catalogue, quantities):
    make_row(channel_idx="other")
    assert _results(staff) == []
