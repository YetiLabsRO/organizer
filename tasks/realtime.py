"""Real-time task-sync helpers shared by the signals and the WebSocket consumer.

The channel layer is treated as **optional infrastructure**, exactly like Celery: if it is not
configured or Redis is unreachable, a broadcast is logged and dropped rather than allowed to fail the
database write that triggered it. See ``tasks/signals.py`` (producers) and ``tasks/consumers.py``
(the ``/ws/tasks/`` consumer that joins these groups).
"""

import logging

from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer

logger = logging.getLogger(__name__)

# Channel-layer message type dispatched to ``TaskEventsConsumer.task_event`` (dots → underscores).
TASK_EVENT_TYPE = "task.event"


def user_group_name(user_id: int) -> str:
    """Every open socket for a user joins this group; task events fan out to it."""
    return f"tasks.user.{user_id}"


def send_to_user(user_id: int, payload: dict) -> None:
    """Fan ``payload`` out to all of a user's connected clients. Never raises.

    Called from synchronous signal handlers (on commit), so it bridges to the async channel layer
    with ``async_to_sync``. A missing layer or a dead Redis is logged and swallowed — a task write
    must never 500 because live sync is down.
    """
    try:
        layer = get_channel_layer()
        if layer is None:
            return
        async_to_sync(layer.group_send)(user_group_name(user_id), {"type": TASK_EVENT_TYPE, "payload": payload})
    except Exception:  # noqa: BLE001 — best-effort broadcast; see module docstring.
        logger.warning("Task event broadcast failed for user %s", user_id, exc_info=True)
