"""WebSocket consumer backing the ``/ws/tasks/`` live task feed.

Auth model: a browser cannot set an ``Authorization`` header on a WebSocket handshake, so the socket
is accepted first and authenticated from its *first message* —
``{"type": "auth", "token": "<drf token>"}``. The DRF token never rides the URL, so it stays out of
access logs and proxy buffers. A socket that stays silent past the grace window, or sends a bad
token, is closed with ``4401``.

Once authenticated the socket joins its owner's group (``tasks.user.<pk>``); task-change events are
pushed to that group by ``tasks/signals.py``.
"""

import asyncio
import logging

from channels.db import database_sync_to_async
from channels.generic.websocket import AsyncJsonWebsocketConsumer
from django.conf import settings
from rest_framework.authtoken.models import Token

from tasks.realtime import user_group_name

logger = logging.getLogger(__name__)

# Application close code (4000–4999 range) meaning "authentication required / failed".
AUTH_FAILED_CODE = 4401
# How long an accepted socket may stay unauthenticated before it is dropped.
DEFAULT_AUTH_GRACE_SECONDS = 5.0


class TaskEventsConsumer(AsyncJsonWebsocketConsumer):
    async def connect(self):
        self.user_id = None
        self.group = None
        await self.accept()
        # Arm the deadline: authenticate within the grace window or be closed.
        grace = getattr(settings, "TASK_WS_AUTH_GRACE_SECONDS", DEFAULT_AUTH_GRACE_SECONDS)
        self._auth_deadline = asyncio.ensure_future(self._enforce_auth_deadline(grace))

    async def disconnect(self, code):
        self._cancel_auth_deadline()
        if self.group is not None:
            await self.channel_layer.group_discard(self.group, self.channel_name)

    async def receive_json(self, content, **kwargs):
        if self.user_id is None:
            await self._handle_auth(content)
            return
        # Lightweight client-driven keepalive; the server otherwise only pushes events.
        if content.get("type") == "ping":
            await self.send_json({"type": "pong"})

    async def _handle_auth(self, content):
        if content.get("type") != "auth":
            # Ignore anything that is not the auth frame while still unauthenticated.
            return
        user_id = await self._resolve_token(content.get("token"))
        if user_id is None:
            await self.close(code=AUTH_FAILED_CODE)
            return
        self.user_id = user_id
        self.group = user_group_name(user_id)
        await self.channel_layer.group_add(self.group, self.channel_name)
        self._cancel_auth_deadline()
        await self.send_json({"type": "auth.ok"})

    async def _enforce_auth_deadline(self, grace):
        try:
            await asyncio.sleep(grace)
        except asyncio.CancelledError:
            return
        if self.user_id is None:
            await self.close(code=AUTH_FAILED_CODE)

    def _cancel_auth_deadline(self):
        deadline = getattr(self, "_auth_deadline", None)
        if deadline is not None and not deadline.done():
            deadline.cancel()

    @database_sync_to_async
    def _resolve_token(self, key):
        """Map a DRF token key to its (active) user id, or None."""
        if not key:
            return None
        try:
            token = Token.objects.select_related("user").get(key=key)
        except Token.DoesNotExist:
            return None
        if not token.user.is_active:
            return None
        return token.user_id

    # Channel-layer handler for messages of type "task.event" (see tasks/realtime.py). The layer
    # dispatches by type with dots mapped to underscores.
    async def task_event(self, event):
        await self.send_json(event["payload"])
