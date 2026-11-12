# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

from typing import Literal

from pydantic import BaseModel, Field


class SubscribeResponse(BaseModel):
    status: Literal["saved"] = Field(description="Same body for a new and an existing request", examples=["saved"])


class CancelResponse(BaseModel):
    status: Literal["cancelled"] = Field(description="Also for an already closed request", examples=["cancelled"])
