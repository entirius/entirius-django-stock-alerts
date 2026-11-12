# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Root URL config: a host includes it with `path("", include("django_stock_alerts.urls"))`."""

from django.urls import include, path

urlpatterns = [path("api/stock-alerts/v2/", include("django_stock_alerts.api.public.urls"))]
