# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

from typing import Literal

from pydantic import BaseModel, ConfigDict, EmailStr, Field


class SubscribeRequest(BaseModel):
    model_config = ConfigDict(extra="ignore")

    email: EmailStr = Field(max_length=254, description="Address to notify", examples=["anna@example.com"])
    sku: str = Field(min_length=1, max_length=255, description="The sold-out variant", examples=["TSHIRT-RED-M"])
    language: str = Field(pattern=r"^[A-Za-z]{2}$", description="Language of the emails", examples=["en"])
    country: str = Field(
        default="", pattern=r"^([A-Za-z]{2})?$", description="Storefront country segment, may be empty", examples=["pl"]
    )
    consent: Literal[True] = Field(description="The person accepted the consent text; must be true", examples=[True])
    consent_text: str = Field(
        min_length=1,
        max_length=2000,
        description="The exact consent text shown",
        examples=["Email me when it is back."],
    )
    website: str = Field(default="", description="Honeypot: leave empty", examples=[""])


class CancelRequest(BaseModel):
    model_config = ConfigDict(extra="ignore")

    token: str = Field(
        min_length=1, max_length=512, description="Signed token from the email link", examples=["WzEs..."]
    )
