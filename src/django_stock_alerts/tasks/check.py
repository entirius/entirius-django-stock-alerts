# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
import logging

from celery import shared_task
from django.core.cache import cache

from django_stock_alerts.services import check_service
from django_stock_alerts.settings import QUEUE

logger = logging.getLogger(__name__)

# Through the Django cache (Redis on a host): two beats never overlap; a crashed run frees it after the timeout.
LOCK_KEY = "django_stock_alerts:check"
LOCK_SECONDS = 4 * 60


@shared_task(name="django_stock_alerts.check", queue=QUEUE)
def check() -> int | None:
    """Beat entry, every 300 s. Returns the number of alerts enqueued; `None` when another run holds the lock."""
    from django_stock_alerts.tasks.send import send_alert

    if not cache.add(LOCK_KEY, 1, LOCK_SECONDS):
        logger.info("event=stock_alerts.check skipped=locked")
        return None
    try:
        result = check_service.run_check(send_alert.delay)
    finally:
        cache.delete(LOCK_KEY)
    logger.info(
        "event=stock_alerts.check channels=%s skus=%s back=%s enqueued=%s",
        ",".join(result.channels) or "-",
        result.skus,
        result.back,
        result.enqueued,
    )
    return result.enqueued
