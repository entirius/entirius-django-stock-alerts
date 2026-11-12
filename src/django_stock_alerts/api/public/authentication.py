# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""The channel key of the subscribe route: an access token with scope ``stock_alerts.subscribe``.

With ``django_access`` installed a request needs the key (401 without one, 403 for a key that may not use this
scope on this channel). Without it the route is open behind its throttles (``docs/install.md``).
"""

from types import SimpleNamespace

from django.apps import apps
from django.contrib.auth.models import AnonymousUser
from rest_framework.authentication import BaseAuthentication
from rest_framework.exceptions import NotAuthenticated, PermissionDenied
from rest_framework.permissions import BasePermission

from django_stock_alerts.apps import SUBSCRIBE_SCOPE

HEADER = "HTTP_X_API_KEY"


def _access_installed() -> bool:
    return apps.is_installed("django_access")


class SubscribeKeyAuthentication(BaseAuthentication):
    """A key valid for the scope on the route's channel authenticates as the anonymous user with the token as auth."""

    def authenticate(self, request):
        key = request.META.get(HEADER)
        if not key or not _access_installed():
            return None
        from django_access.services.tokens import verify_api_key

        channel_idx = (request.parser_context or {}).get("kwargs", {}).get("channel_idx")
        token = verify_api_key(SimpleNamespace(META={HEADER: key}), SUBSCRIBE_SCOPE, channel_idx)
        return None if token is None else (AnonymousUser(), token)

    def authenticate_header(self, request) -> str:
        return "X-API-KEY"


class HasSubscribeKey(BasePermission):
    def has_permission(self, request, view) -> bool:
        if not _access_installed() or request.auth is not None:
            return True
        if not request.META.get(HEADER):
            raise NotAuthenticated("API key required.")
        raise PermissionDenied("API key not valid for this route.")
