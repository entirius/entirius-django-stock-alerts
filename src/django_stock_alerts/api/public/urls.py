# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

from django.urls import path

from django_stock_alerts.api.public.views import CancelView, SubscribeView

urlpatterns = [
    path("<str:channel_idx>/subscriptions/", SubscribeView.as_view(), name="stock-alerts-subscribe"),
    path("<str:channel_idx>/subscriptions/cancel/", CancelView.as_view(), name="stock-alerts-cancel"),
]
