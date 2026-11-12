# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
import logging

from celery import shared_task

from django_stock_alerts import settings as stock_settings
from django_stock_alerts.services import alert_service
from django_stock_alerts.settings import QUEUE

logger = logging.getLogger(__name__)

# One countdown per retry (max_retries = 3).
RETRY_COUNTDOWNS = (120, 600, 1800)
_TASK_OPTIONS = {
    "bind": True,
    "queue": QUEUE,
    "acks_late": True,
    "rate_limit": stock_settings.SEND_RATE,  # per worker process, not global
    "max_retries": len(RETRY_COUNTDOWNS),
}


@shared_task(name="django_stock_alerts.send_alert", **_TASK_OPTIONS)
def send_alert(self, subscription_id: int) -> str:
    try:
        return alert_service.send_alert(subscription_id)
    except alert_service.RETRYABLE_ERRORS as exc:
        if self.request.retries >= self.max_retries:
            alert_service.record_failed_delivery(subscription_id)
            return "failed"
        raise self.retry(exc=exc, countdown=RETRY_COUNTDOWNS[self.request.retries]) from exc


@shared_task(name="django_stock_alerts.send_signup", **_TASK_OPTIONS)
def send_signup(self, subscription_id: int) -> None:
    """A lost signup email never changes the request: after the last retry it is logged and dropped."""
    try:
        alert_service.send_signup(subscription_id)
    except alert_service.RETRYABLE_ERRORS as exc:
        if self.request.retries >= self.max_retries:
            logger.warning("stock alerts: request %s signup email failed: %s", subscription_id, type(exc).__name__)
            return
        raise self.retry(exc=exc, countdown=RETRY_COUNTDOWNS[self.request.retries]) from exc
