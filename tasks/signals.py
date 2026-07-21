"""Real-time task-sync signal handlers.

``post_save`` / ``post_delete`` on ``TaskItem`` are the single choke point that catches *every* task
write — the REST API, the MCP server, Celery recurring-task generation, and the Django admin all
funnel through ``Model.save()`` / ``.delete()``. Each handler defers its broadcast to
``transaction.on_commit`` so that:

* rolled-back writes never reach a client, and
* the payload reflects committed state — including tags a project inherits onto the task *after*
  ``super().save()`` (see ``TaskItem.save``) and tags a DRF serializer sets *after* it calls
  ``.save()``. The on-commit re-read picks those up regardless of ordering.

We deliberately do **not** hook ``m2m_changed`` on the tags. Every supported way to change a task's
tags runs through ``TaskItem.save()`` first (DRF calls ``instance.save()`` before assigning m2m; the
model inherits project tags inside ``save()``), which bumps ``changed_date`` and fires ``post_save``.
A bare tag mutation leaves ``changed_date`` untouched, so the client's stale-event guard would drop
it anyway — hooking it would only emit redundant events.
"""

from django.db import transaction
from django.db.models.signals import post_delete, post_save
from django.dispatch import receiver

from tasks.models import TaskItem
from tasks.realtime import send_to_user


def _broadcast_saved(task_id, owner_id, created):
    """Re-read the committed task and push it to its owner's connected clients."""
    # Local import: the serializer module pulls in models/recurrence, so keep it off module load.
    from tasks.api.serializers import TaskListSerializer

    task = TaskItem.objects.filter(pk=task_id).first()
    if task is None:
        # Deleted later in the same transaction — the delete handler covers it.
        return
    send_to_user(
        owner_id,
        {
            "type": "task.created" if created else "task.updated",
            "id": task_id,
            "task": dict(TaskListSerializer(task).data),
        },
    )


@receiver(post_save, sender=TaskItem, dispatch_uid="tasks.realtime.task_saved")
def task_saved(sender, instance, created, **kwargs):
    owner_id = instance.owner_id
    if owner_id is None:
        # An ownerless task belongs to no group — nobody to notify.
        return
    task_id = instance.pk
    transaction.on_commit(lambda: _broadcast_saved(task_id, owner_id, created))


@receiver(post_delete, sender=TaskItem, dispatch_uid="tasks.realtime.task_deleted")
def task_deleted(sender, instance, **kwargs):
    owner_id = instance.owner_id
    if owner_id is None:
        return
    task_id = instance.pk
    # The row is gone by commit time, so capture id/owner now and send only the id.
    transaction.on_commit(lambda: send_to_user(owner_id, {"type": "task.deleted", "id": task_id}))
