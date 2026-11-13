# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
import pytest
from django.utils import timezone

from django_stock_alerts.enums import CancelReason, Status
from django_stock_alerts.models import Subscription
from tests.admin.conftest import admin_url, make_row
from tests.conftest import EMAIL, SKU_2

pytestmark = pytest.mark.django_db

LIST = admin_url("subscriptions/")


def _ids(client, **params) -> list[int]:
    response = client.get(LIST, params)
    assert response.status_code == 200, response.content
    return [row["id"] for row in response.json()["results"]]


def test_row_shape(staff, catalogue):
    row = make_row()
    result = staff.get(LIST).json()["results"][0]
    assert result["id"] == row.pk
    assert (result["email"], result["status"], result["product_name"], result["variant_line"]) == (
        EMAIL,
        "waiting",
        "Red T-shirt",
        "Size: M",
    )
    assert set(result) == {
        "id", "sku", "product_name", "variant_line", "email", "language",
        "status", "created", "notified_at", "cancelled_at", "cancel_reason",
    }  # fmt: skip


def test_filter_by_status(staff, catalogue):
    make_row()
    notified = make_row(email="b@example.com", status=Status.NOTIFIED, notified_at=timezone.now())
    assert _ids(staff, status="notified") == [notified.pk]


def test_unknown_status_is_400(staff):
    assert staff.get(LIST, {"status": "lost"}).status_code == 400


def test_filter_by_sku(staff, catalogue):
    make_row()
    other = make_row(sku=SKU_2)
    assert _ids(staff, sku=SKU_2) == [other.pk]


def test_search_by_exact_address_any_case(staff, catalogue):
    row = make_row()
    make_row(email="anna.other@example.com")
    assert _ids(staff, search=EMAIL.upper()) == [row.pk]
    assert _ids(staff, search="anna") == []  # no substring search on addresses


def test_search_by_sku_prefix(staff, catalogue):
    make_row()
    other = make_row(sku=SKU_2)
    assert _ids(staff, search=SKU_2) == [other.pk]


def test_default_order_newest_first_and_ordering(staff, catalogue):
    first, second = make_row(), make_row(sku=SKU_2)
    assert _ids(staff) == [second.pk, first.pk]
    assert _ids(staff, ordering="created") == [first.pk, second.pk]


@pytest.mark.parametrize("ordering", ["email", "-status", "created_at"])
def test_bad_ordering_is_400(staff, ordering):
    assert staff.get(LIST, {"ordering": ordering}).status_code == 400


def test_another_channels_rows_never_appear(staff, catalogue):
    make_row(channel_idx="other")
    assert _ids(staff) == []
    assert _ids(staff, search=EMAIL) == []


def test_cancel_a_waiting_request(staff, catalogue):
    row = make_row()
    response = staff.post(admin_url(f"subscriptions/{row.pk}/cancel/"))
    assert (response.status_code, response.json()["status"], response.json()["cancel_reason"]) == (
        200,
        "cancelled",
        "admin",
    )
    row.refresh_from_db()
    assert (row.status, row.cancel_reason) == (Status.CANCELLED, CancelReason.ADMIN)


def test_cancel_a_closed_request_leaves_it(staff, catalogue):
    row = make_row(status=Status.NOTIFIED, notified_at=timezone.now())
    response = staff.post(admin_url(f"subscriptions/{row.pk}/cancel/"))
    assert (response.status_code, response.json()["status"]) == (200, "notified")
    assert Subscription.objects.get(pk=row.pk).cancel_reason == ""


def test_cancel_of_another_channel_is_404(staff, catalogue):
    row = make_row(channel_idx="other")
    assert staff.post(admin_url(f"subscriptions/{row.pk}/cancel/")).status_code == 404
    assert Subscription.objects.get(pk=row.pk).status == Status.WAITING
