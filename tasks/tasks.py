"""Celery tasks for the ``tasks`` app.

The heavy lifting lives in ``tasks/recurrence.py`` (framework-free, unit-tested). This module is just
the Celery entry point that celery beat invokes on a schedule; the same logic is also reachable via
the ``generate_recurring_tasks`` management command.
"""

import logging

from celery import shared_task
from django.db import transaction
from django.utils import timezone

from tasks import recurrence
from tasks.models import TaskTemplate

logger = logging.getLogger(__name__)


@shared_task(name="tasks.generate_recurring_tasks")
def generate_recurring_tasks() -> int:
    """Materialize due tasks for every active template. Returns the number of tasks created.

    Each template is processed in its own transaction so one bad template cannot abort the batch.
    """
    today = timezone.localdate()
    created = 0
    for template in TaskTemplate.objects.filter(is_active=True):
        try:
            with transaction.atomic():
                if recurrence.materialize_due_tasks(template, today) is not None:
                    created += 1
        except Exception:  # noqa: BLE001 - never let one template break the scheduled run
            logger.exception("Failed to generate task for template %s (id=%s)", template, template.pk)
    return created
