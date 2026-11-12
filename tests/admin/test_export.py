# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
import csv
import io

import pytest
from django.utils import timezone

from django_stock_alerts.enums import Status
from django_stock_alerts.gdpr import anonymised_address, gdpr_erase
from tests.admin.conftest import admin_url, make_row
from tests.conftest import EMAIL, SKU, SKU_2

pytestmark = pytest.mark.django_db

EXPORT = admin_url("subscriptions/export/")
HEADER = ["sku", "product_name", "variant_line", "email", "language", "status", "created", "notified_at"]


def _rows(client, **params) -> list[list[str]]:
    response = client.get(EXPORT, params)
    assert response.status_code == 200
    assert response["Content-Type"] == "text/csv"
    assert "attachment" in response["Content-Disposition"]
    return list(csv.reader(io.StringIO(b"".join(response.streaming_content).decode())))


def test_header_and_a_row(staff, catalogue):
    make_row()
    header, row = _rows(staff)
    assert header == HEADER
    assert row[:6] == [SKU, "Red T-shirt", "Size: M", EMAIL, "en", "waiting"]
    assert row[7] == ""


def test_filtered_rows(staff, catalogue):
    make_row()
    make_row(sku=SKU_2, email="b@example.com", status=Status.NOTIFIED, notified_at=timezone.now())
    make_row(channel_idx="other")
    assert [row[0] for row in _rows(staff, status="notified")[1:]] == [SKU_2]
    assert [row[0] for row in _rows(staff, sku=SKU)[1:]] == [SKU]
    assert [row[3] for row in _rows(staff, search="B@example.com")[1:]] == ["b@example.com"]


def test_formula_guard(staff, catalogue):
    for index, prefix in enumerate("=+-@"):
        make_row(sku=f"{prefix}SUM(A{index})")
    skus = sorted(row[0] for row in _rows(staff)[1:])
    assert all(sku.startswith("'") for sku in skus)
    assert "'=SUM(A0)" in skus


def test_anonymised_rows_export_their_token(staff, catalogue):
    make_row()
    gdpr_erase(EMAIL)
    (row,) = _rows(staff)[1:]
    assert row[3] == anonymised_address(EMAIL)


def test_bad_filter_is_400(staff):
    assert staff.get(EXPORT, {"status": "lost"}).status_code == 400
