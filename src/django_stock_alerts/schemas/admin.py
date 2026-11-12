# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
"""Admin panel queries and rows. The `ordering` literals are the allowlists: anything else is a 400."""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from django_stock_alerts.enums import Status

DemandOrdering = Literal["waiting", "-waiting", "oldest_request", "-oldest_request", "sku"]
SubscriptionOrdering = Literal["created", "-created", "notified_at", "-notified_at"]


class DemandQuery(BaseModel):
    model_config = ConfigDict(extra="ignore")

    search: str = Field(default="", max_length=255, description="SKU prefix or part of the product name")
    ordering: DemandOrdering = Field(default="-waiting", description="Sort key")


class ExportQuery(BaseModel):
    model_config = ConfigDict(extra="ignore")

    status: Status | None = Field(default=None, description="Only requests of this status")
    sku: str = Field(default="", max_length=255, description="Only requests of this exact SKU")
    search: str = Field(default="", max_length=254, description="Exact address (any case) or SKU prefix")


class SubscriptionsQuery(ExportQuery):
    ordering: SubscriptionOrdering = Field(default="-created", description="Sort key")


class DemandRow(BaseModel):
    sku: str = Field(description="The variant waited for", examples=["TSHIRT-RED-M"])
    parent_sku: str = Field(description="Its configurable parent, may be empty", examples=["TSHIRT"])
    product_name: str | None = Field(description="Null when the SKU is gone from the catalogue", examples=["T-shirt"])
    variant_line: str | None = Field(description="Variant attributes, e.g. the size", examples=["Size: M"])
    waiting: int = Field(description="Waiting requests", examples=[4])
    oldest_request: datetime = Field(description="Creation time of the oldest waiting request")
    quantity: int = Field(description="Saleable pieces now; 0 = sold out", examples=[0])
    notified_30d: int = Field(description="Requests notified in the last 30 days", examples=[2])


class DemandListResponse(BaseModel):
    count: int = Field(description="Variants waited for (matching the search)", examples=[1])
    total_waiting: int = Field(description="Waiting requests across those variants", examples=[4])
    next: str | None = Field(description="Next page URL", examples=[None])
    previous: str | None = Field(description="Previous page URL", examples=[None])
    results: list[DemandRow]


class SubscriptionRow(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int = Field(examples=[7])
    sku: str = Field(examples=["TSHIRT-RED-M"])
    product_name: str | None = Field(default=None, examples=["T-shirt"])
    variant_line: str | None = Field(default=None, examples=["Size: M"])
    email: str = Field(description="The address, or its anonymised token", examples=["anna@example.com"])
    language: str = Field(examples=["en"])
    status: Status
    created: datetime
    notified_at: datetime | None
    cancelled_at: datetime | None
    cancel_reason: str = Field(description="user, admin, undeliverable, erased; empty while open", examples=[""])


class SubscriptionListResponse(BaseModel):
    count: int = Field(description="Matching requests", examples=[1])
    next: str | None = Field(description="Next page URL", examples=[None])
    previous: str | None = Field(description="Previous page URL", examples=[None])
    results: list[SubscriptionRow]
