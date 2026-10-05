"""Celery entry points for the VolunHub sync.

The logic lives in ``sync.py``; these are the handles beat and the API call. Every connection is
isolated so one broken account cannot abort a scheduled batch.
"""

import logging

from celery import shared_task

from integrations.volunhub.models import VolunHubConnection

logger = logging.getLogger(__name__)


@shared_task(name="integrations.volunhub.sync_all")
def sync_all():
    """Sync every connection that does not need re-authorization. Returns how many were processed."""
    from integrations.volunhub.sync import sync_connection

    processed = 0
    connections = VolunHubConnection.objects.exclude(status=VolunHubConnection.NEEDS_REAUTH).select_related(
        "user", "client"
    )
    for connection in connections:
        try:
            sync_connection(connection)
            processed += 1
        except Exception:  # noqa: BLE001 - never let one connection break the scheduled run
            logger.exception("VolunHub sync failed for %s", connection.user)
    return processed


@shared_task(name="integrations.volunhub.sync_one")
def sync_one(connection_id):
    from integrations.volunhub.sync import sync_connection

    connection = VolunHubConnection.objects.filter(pk=connection_id).select_related("user", "client").first()
    if connection is None:
        return None
    return str(sync_connection(connection))
