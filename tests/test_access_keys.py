# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""With django_access installed the subscribe route needs the channel key (scope `stock_alerts.subscribe`)."""

import pytest
from rest_framework.test import APIClient

from django_stock_alerts.apps import SUBSCRIBE_SCOPE
from tests.conftest import WITH_ACCESS, body, cancel_url, subscribe_url

pytestmark = [pytest.mark.django_db, pytest.mark.skipif(not WITH_ACCESS, reason="django_access is not installed")]


def test_without_a_key(products, quantities):
    response = APIClient().post(subscribe_url(), body(), format="json")
    assert response.status_code == 401


def test_with_a_key_of_another_scope(products, quantities):
    from django_access.catalogue import registry
    from django_access.models import Application
    from django_access.services.access_service import Actor
    from django_access.services.tokens import issue_token

    other = next(scope.key for scope in registry.scopes() if scope.publishable and scope.key != SUBSCRIBE_SCOPE)
    application = Application.objects.create(name="other-scope")
    _, raw = issue_token(application, scopes=[other], channel_idx="default-europe", actor=Actor())
    response = APIClient().post(subscribe_url(), body(), format="json", HTTP_X_API_KEY=raw)
    assert response.status_code == 403


def test_with_the_key(api, products, quantities):
    assert api.post(subscribe_url(), body(), format="json").status_code == 201


def test_cancel_needs_no_key(products, quantities):
    assert APIClient().post(cancel_url(), {"token": "x"}, format="json").status_code == 400
