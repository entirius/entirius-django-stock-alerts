# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
"""Admin routes of the CMS panel "Stock alerts": demand per variant, the request list, its CSV export, cancel.

Every view: JWT, `IsAdminUser`, area `stock_alerts.subscriptions` (read; cancel is a POST, so write).
"""

import csv
from collections.abc import Iterator
from typing import TypeVar

from django.db.models import QuerySet
from django.http import StreamingHttpResponse
from django_utils.api.v2_errors import ErrorResponse, raise_pydantic_as_drf
from drf_spectacular.utils import OpenApiParameter, OpenApiResponse, extend_schema
from pydantic import BaseModel, ValidationError
from rest_framework.exceptions import NotFound
from rest_framework.pagination import PageNumberPagination
from rest_framework.permissions import IsAdminUser
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.authentication import JWTAuthentication

from django_stock_alerts.models import Subscription
from django_stock_alerts.schemas.admin import (
    DemandListResponse,
    DemandQuery,
    DemandRow,
    ExportQuery,
    SubscriptionListResponse,
    SubscriptionRow,
    SubscriptionsQuery,
)
from django_stock_alerts.services import admin_queries
from django_stock_alerts.services.admin_queries import UNKNOWN, Description, SubscriptionFilters

SchemaT = TypeVar("SchemaT", bound=BaseModel)

AREA = "stock_alerts.subscriptions"
TAGS = ["Back-in-stock alerts (admin)"]
CHANNEL = OpenApiParameter(name="channel_idx", location="path", type=str, description="Channel identifier")
PAGE = [
    OpenApiParameter("page", int, description="Page number"),
    OpenApiParameter("page_size", int, description="Rows per page, ≤ 100"),
]
FILTERS = [
    CHANNEL,
    OpenApiParameter("status", str, enum=["waiting", "notified", "cancelled", "expired"], description="Status"),
    OpenApiParameter("sku", str, description="Exact SKU"),
    OpenApiParameter("search", str, description="Exact address (any case) or SKU prefix"),
]
ERRORS = {
    400: OpenApiResponse(ErrorResponse, description="Invalid filter or ordering"),
    401: OpenApiResponse(ErrorResponse, description="Not authenticated"),
    403: OpenApiResponse(ErrorResponse, description="Not staff, or no permission on the area"),
}
CSV_COLUMNS = ["sku", "product_name", "variant_line", "email", "language", "status", "created", "notified_at"]
_FORMULA_PREFIXES = ("=", "+", "-", "@", "\t", "\r")


class AdminPagination(PageNumberPagination):
    page_size = 20
    page_size_query_param = "page_size"
    max_page_size = 100


class AdminView(APIView):
    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAdminUser]
    access_area = AREA


def _parse(schema: type[SchemaT], request: Request) -> SchemaT:
    try:
        return schema.model_validate(request.query_params.dict())
    except ValidationError as exc:
        raise_pydantic_as_drf(exc)


def _filters(query: ExportQuery, ordering: str = "-created") -> SubscriptionFilters:
    return SubscriptionFilters(status=query.status, sku=query.sku, search=query.search, ordering=ordering)


def _subscription_row(row: Subscription, described: Description = UNKNOWN) -> SubscriptionRow:
    return SubscriptionRow(
        id=row.pk,
        sku=row.sku,
        product_name=described.name,
        variant_line=described.variant_line,
        email=row.email,
        language=row.language,
        status=row.status,
        created=row.created_at,
        notified_at=row.notified_at,
        cancelled_at=row.cancelled_at,
        cancel_reason=row.cancel_reason,
    )


def _demand_rows(channel_idx: str, page: list[dict]) -> list[DemandRow]:
    skus = [row["sku"] for row in page]
    described, stock = admin_queries.describe(channel_idx, skus), admin_queries.quantities(channel_idx, skus)
    return [
        DemandRow(
            **row,
            product_name=described.get(row["sku"], UNKNOWN).name,
            variant_line=described.get(row["sku"], UNKNOWN).variant_line,
            quantity=stock[row["sku"]],
        )
        for row in page
    ]


class DemandView(AdminView):
    @extend_schema(
        summary="Variants customers wait for",
        description="One row per SKU with waiting requests; the stock now and the requests notified in 30 days.",
        tags=TAGS,
        parameters=[
            CHANNEL,
            OpenApiParameter("search", str, description="SKU prefix or part of the product name"),
            OpenApiParameter("ordering", str, enum=["waiting", "-waiting", "oldest_request", "-oldest_request", "sku"]),
            *PAGE,
        ],
        responses={200: DemandListResponse, **ERRORS},
    )
    def get(self, request: Request, channel_idx: str) -> Response:
        query = _parse(DemandQuery, request)
        rows = admin_queries.demand(channel_idx, query.search, query.ordering)
        paginator = AdminPagination()
        page = paginator.paginate_queryset(rows, request, view=self)
        payload = DemandListResponse(
            count=paginator.page.paginator.count,
            total_waiting=admin_queries.total_waiting(rows),
            next=paginator.get_next_link(),
            previous=paginator.get_previous_link(),
            results=_demand_rows(channel_idx, page),
        )
        return Response(payload.model_dump(mode="json"))


class SubscriptionListView(AdminView):
    @extend_schema(
        summary="Back-in-stock requests",
        description="Newest first by default, paginated. Search matches an exact address or a SKU prefix.",
        tags=TAGS,
        parameters=[
            *FILTERS,
            OpenApiParameter("ordering", str, enum=["created", "-created", "notified_at", "-notified_at"]),
            *PAGE,
        ],
        responses={200: SubscriptionListResponse, **ERRORS},
    )
    def get(self, request: Request, channel_idx: str) -> Response:
        query = _parse(SubscriptionsQuery, request)
        rows = admin_queries.subscriptions(channel_idx, _filters(query, query.ordering))
        paginator = AdminPagination()
        page = paginator.paginate_queryset(rows, request, view=self)
        described = admin_queries.describe(channel_idx, (row.sku for row in page))
        payload = SubscriptionListResponse(
            count=paginator.page.paginator.count,
            next=paginator.get_next_link(),
            previous=paginator.get_previous_link(),
            results=[_subscription_row(row, described.get(row.sku, UNKNOWN)) for row in page],
        )
        return Response(payload.model_dump(mode="json"))


class _Echo:
    """Pseudo-buffer: csv.writer returns each formatted line instead of storing it."""

    def write(self, value: str) -> str:
        return value


def _csv_safe(value: object) -> str:
    """Prefix formula-injection characters so a spreadsheet never runs them."""
    text = "" if value is None else str(value)
    return f"'{text}" if text.startswith(_FORMULA_PREFIXES) else text


def _csv_lines(channel_idx: str, rows: QuerySet) -> Iterator[str]:
    writer = csv.writer(_Echo())
    yield writer.writerow(CSV_COLUMNS)
    for row, described in admin_queries.subscriptions_described(channel_idx, rows):
        data = _subscription_row(row, described).model_dump(mode="json")
        yield writer.writerow([_csv_safe(data[column]) for column in CSV_COLUMNS])


class ExportView(AdminView):
    @extend_schema(
        summary="Export back-in-stock requests as CSV",
        description="Streams the filtered requests, newest first. Columns: " + ", ".join(CSV_COLUMNS) + ".",
        tags=TAGS,
        parameters=FILTERS,
        responses={200: OpenApiResponse(description="CSV file download"), **ERRORS},
    )
    def get(self, request: Request, channel_idx: str) -> StreamingHttpResponse:
        rows = admin_queries.subscriptions(channel_idx, _filters(_parse(ExportQuery, request)))
        response = StreamingHttpResponse(_csv_lines(channel_idx, rows), content_type="text/csv")
        response["Content-Disposition"] = 'attachment; filename="stock-alerts.csv"'
        return response


class CancelView(AdminView):
    @extend_schema(
        summary="Cancel a back-in-stock request",
        description="Reason `admin`. A request that is no longer waiting comes back unchanged.",
        tags=TAGS,
        parameters=[CHANNEL],
        request=None,
        responses={200: SubscriptionRow, 404: OpenApiResponse(ErrorResponse, description="Unknown request"), **ERRORS},
    )
    def post(self, request: Request, channel_idx: str, pk: int) -> Response:
        try:
            row = admin_queries.cancel(channel_idx, pk)
        except Subscription.DoesNotExist:
            raise NotFound("Request not found.") from None
        described = admin_queries.describe(channel_idx, [row.sku]).get(row.sku, UNKNOWN)
        return Response(_subscription_row(row, described).model_dump(mode="json"))
