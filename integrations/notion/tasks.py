"""Celery entry points for the Notion sync.

Mirrors ``tasks/tasks.py``: the logic lives in ``sync.py``, and these are just the handles beat and
the API call. Every connection is isolated so one broken account cannot abort a scheduled batch.
"""

import logging

from celery import shared_task

from integrations.notion.models import NotionConnection

logger = logging.getLogger(__name__)


@shared_task(name="integrations.notion.sync_all")
def sync_all(full=False):
    """Sync every connection that has a database. Returns how many were processed."""
    from integrations.notion.sync import sync_connection

    processed = 0
    connections = NotionConnection.objects.exclude(status=NotionConnection.NEEDS_REAUTH).select_related(
        "database", "user"
    )
    for connection in connections:
        if getattr(connection, "database", None) is None:
            continue
        try:
            sync_connection(connection, full=full)
            processed += 1
        except Exception:  # noqa: BLE001 - never let one connection break the scheduled run
            logger.exception("Notion sync failed for %s", connection.user)
    return processed


@shared_task(name="integrations.notion.sync_one")
def sync_one(connection_id, full=False):
    from integrations.notion.sync import sync_connection

    connection = NotionConnection.objects.filter(pk=connection_id).select_related("database", "user").first()
    if connection is None:
        return None
    return str(sync_connection(connection, full=full))


@shared_task(name="integrations.notion.bootstrap_connection")
def bootstrap_connection(connection_id):
    """Upload the user's existing tasks into the freshly created, empty database."""
    from integrations.notion.sync import sync_connection

    connection = NotionConnection.objects.filter(pk=connection_id).select_related("database", "user").first()
    if connection is None:
        return None
    return str(sync_connection(connection))
