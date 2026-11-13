# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
from django.urls import path

from django_stock_alerts.api.admin.views import CancelView, DemandView, ExportView, SubscriptionListView

urlpatterns = [
    path("<str:channel_idx>/demand/", DemandView.as_view(), name="stock-alerts-admin-demand"),
    path("<str:channel_idx>/subscriptions/", SubscriptionListView.as_view(), name="stock-alerts-admin-subscriptions"),
    path("<str:channel_idx>/subscriptions/export/", ExportView.as_view(), name="stock-alerts-admin-export"),
    path("<str:channel_idx>/subscriptions/<int:pk>/cancel/", CancelView.as_view(), name="stock-alerts-admin-cancel"),
]
