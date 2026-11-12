# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
import logging

from celery import shared_task

from django_stock_alerts.services import retention_service
from django_stock_alerts.settings import QUEUE

logger = logging.getLogger(__name__)


@shared_task(name="django_stock_alerts.retention", queue=QUEUE)
def retention() -> dict[str, int]:
    """Beat entry, daily (03:30)."""
    result = retention_service.run_retention()
    logger.info("event=stock_alerts.retention expired=%s anonymised=%s", result.expired, result.anonymised)
    return {"expired": result.expired, "anonymised": result.anonymised}
