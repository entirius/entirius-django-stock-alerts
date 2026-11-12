# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Public routes of the storefront: save a back-in-stock request, cancel it from the email link.

Answers never tell whether the address already had a request: a new, an existing and a honeypot request get the
same 201 body.
"""

import ipaddress
import logging
import uuid

from django.db import transaction
from django_utils.api.client_ip import get_client_ip
from django_utils.api.v2_errors import ErrorResponse, raise_pydantic_as_drf
from drf_spectacular.utils import OpenApiParameter, OpenApiResponse, extend_schema
from pydantic import BaseModel, ValidationError
from rest_framework import status
from rest_framework.exceptions import APIException, NotFound, ParseError
from rest_framework.permissions import AllowAny
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from django_stock_alerts import settings as stock_settings
from django_stock_alerts.api.public.authentication import HasSubscribeKey, SubscribeKeyAuthentication
from django_stock_alerts.api.public.throttling import CancelThrottle, SubscribeAddressThrottle, SubscribeThrottle
from django_stock_alerts.schemas.requests import CancelRequest, SubscribeRequest
from django_stock_alerts.schemas.responses import CancelResponse, SubscribeResponse
from django_stock_alerts.services import subscription_service, token_service
from django_stock_alerts.services.subscription_service import SubscribeData
from django_stock_alerts.tasks.send import send_signup

logger = logging.getLogger(__name__)

TAGS = ["Back-in-stock alerts"]
CHANNEL = OpenApiParameter(name="channel_idx", location="path", type=str, description="Channel identifier")
USER_AGENT_MAX = 2048


class InStockConflict(APIException):
    status_code = status.HTTP_409_CONFLICT
    default_detail = "The variant can be bought now."
    default_code = "in_stock"


def _parse(schema: type[BaseModel], data) -> BaseModel:
    try:
        return schema.model_validate(data)
    except ValidationError as exc:
        raise_pydantic_as_drf(exc)


def _open_channel(channel_idx: str) -> None:
    try:
        subscription_service.ensure_channel_open(channel_idx)
    except subscription_service.ChannelClosed:
        raise NotFound("Unknown channel.") from None


def _too_many() -> Response:
    body = ErrorResponse(
        error="TOO_MANY_REQUESTS", message="Too many waiting requests for this address.", debug_id=uuid.uuid4().hex[:8]
    )
    return Response(body.model_dump(), status=status.HTTP_429_TOO_MANY_REQUESTS)


def _saved() -> Response:
    return Response(SubscribeResponse(status="saved").model_dump(), status=status.HTTP_201_CREATED)


def _client_ip(request: Request) -> str | None:
    """The consent record stores an IP column: a forwarded list or a forged header value is stored as no IP."""
    candidate = get_client_ip(request)
    try:
        return str(ipaddress.ip_address(candidate))
    except ValueError:
        return None


def _subscribe_data(request: Request, channel_idx: str, body: SubscribeRequest) -> SubscribeData:
    return SubscribeData(
        channel_idx=channel_idx,
        sku=body.sku,
        email=body.email,
        language=body.language,
        country=body.country,
        consent_text=body.consent_text,
        ip_address=_client_ip(request),
        user_agent=request.META.get("HTTP_USER_AGENT", "")[:USER_AGENT_MAX],
    )


class SubscribeView(APIView):
    authentication_classes = [SubscribeKeyAuthentication]
    permission_classes = [HasSubscribeKey]
    throttle_classes = [SubscribeThrottle, SubscribeAddressThrottle]

    @extend_schema(
        summary="Save a back-in-stock request",
        description=(
            "One waiting request per address and variant: a repeated request answers the same 201. "
            "Needs the channel key (X-API-KEY, scope stock_alerts.subscribe) where access is installed. "
            "Limited per client address and per e-mail address (429)."
        ),
        tags=TAGS,
        auth=[],
        parameters=[CHANNEL],
        request=SubscribeRequest,
        responses={
            201: SubscribeResponse,
            400: OpenApiResponse(ErrorResponse, description="Validation error"),
            401: OpenApiResponse(ErrorResponse, description="Missing API key"),
            403: OpenApiResponse(ErrorResponse, description="API key not valid for this route"),
            404: OpenApiResponse(ErrorResponse, description="Unknown channel or SKU"),
            409: OpenApiResponse(ErrorResponse, description="IN_STOCK: the variant can be bought now"),
            429: OpenApiResponse(ErrorResponse, description="Throttled, or TOO_MANY_REQUESTS for the address"),
        },
    )
    def post(self, request: Request, channel_idx: str) -> Response:
        _open_channel(channel_idx)
        body = _parse(SubscribeRequest, request.data)
        if body.website:
            logger.info("stock alerts: honeypot request dropped")
            return _saved()
        try:
            row, created = subscription_service.subscribe(_subscribe_data(request, channel_idx, body))
        except subscription_service.ProductNotFound:
            raise NotFound("Unknown SKU.") from None
        except subscription_service.InStock:
            raise InStockConflict from None
        except subscription_service.TooManyRequests:
            return _too_many()
        if created and stock_settings.SIGNUP_EMAIL:
            transaction.on_commit(lambda: send_signup.delay(row.pk))
        return _saved()


class CancelView(APIView):
    """The signed token from the email link is the credential."""

    authentication_classes = []
    permission_classes = [AllowAny]
    throttle_classes = [CancelThrottle]

    @extend_schema(
        summary="Cancel a back-in-stock request",
        description="Cancels the request of the token. An already closed request answers the same 200.",
        tags=TAGS,
        auth=[],
        parameters=[CHANNEL],
        request=CancelRequest,
        responses={
            200: CancelResponse,
            400: OpenApiResponse(ErrorResponse, description="Bad token"),
            404: OpenApiResponse(ErrorResponse, description="Unknown channel"),
            429: OpenApiResponse(ErrorResponse, description="Throttled"),
        },
    )
    def post(self, request: Request, channel_idx: str) -> Response:
        _open_channel(channel_idx)
        body = _parse(CancelRequest, request.data)
        try:
            subscription_service.cancel_by_token(channel_idx, body.token)
        except token_service.BadToken:
            raise ParseError("Invalid token.") from None
        return Response(CancelResponse(status="cancelled").model_dump())
