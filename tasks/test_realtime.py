"""Tests for real-time task sync (WebSocket consumer + broadcast signals).

CI has no Redis service container, so every test overrides ``CHANNEL_LAYERS`` to the in-memory
backend. The Redis layer is exercised in staging/production, not here.
"""

from unittest import mock

from channels.layers import get_channel_layer

# Import from the submodule, not channels.testing, whose __init__ pulls in a daphne-only
# live-server test class that we don't have (and don't need — uvicorn serves prod).
from channels.testing.websocket import WebsocketCommunicator
from django.contrib.auth import get_user_model
from django.test import TestCase, TransactionTestCase, override_settings
from rest_framework.authtoken.models import Token

from organizer.asgi import application
from tasks.models import Project, Tag, TaskItem
from tasks.realtime import send_to_user, user_group_name

User = get_user_model()

IN_MEMORY_LAYER = {"default": {"BACKEND": "channels.layers.InMemoryChannelLayer"}}


@override_settings(CHANNEL_LAYERS=IN_MEMORY_LAYER)
class BroadcastSignalTests(TestCase):
    """The post_save/post_delete signals fan the right payload to the owner, on commit only."""

    def setUp(self):
        self.owner = User.objects.create_user(username="owner", password="pw")

    def test_create_broadcasts_created_to_owner(self):
        with mock.patch("tasks.signals.send_to_user") as send:
            with self.captureOnCommitCallbacks(execute=True):
                task = TaskItem.objects.create(title="hello", owner=self.owner)

        send.assert_called_once()
        user_id, payload = send.call_args.args
        self.assertEqual(user_id, self.owner.id)
        self.assertEqual(payload["type"], "task.created")
        self.assertEqual(payload["id"], task.id)
        self.assertEqual(payload["task"]["title"], "hello")

    def test_update_broadcasts_updated(self):
        task = TaskItem.objects.create(title="t", owner=self.owner)
        with mock.patch("tasks.signals.send_to_user") as send:
            with self.captureOnCommitCallbacks(execute=True):
                task.title = "renamed"
                task.save()

        user_id, payload = send.call_args.args
        self.assertEqual(payload["type"], "task.updated")
        self.assertEqual(payload["task"]["title"], "renamed")

    def test_delete_broadcasts_id_only(self):
        task = TaskItem.objects.create(title="t", owner=self.owner)
        task_id = task.id
        with mock.patch("tasks.signals.send_to_user") as send:
            with self.captureOnCommitCallbacks(execute=True):
                task.delete()

        send.assert_called_once_with(self.owner.id, {"type": "task.deleted", "id": task_id})

    def test_payload_includes_project_inherited_tags(self):
        # TaskItem.save() attaches the project's tags *after* super().save(); the on-commit re-read
        # must still capture them.
        tag = Tag.objects.create(name="inherited")
        project = Project.objects.create(title="proj")
        project.tags.add(tag)
        with mock.patch("tasks.signals.send_to_user") as send:
            with self.captureOnCommitCallbacks(execute=True):
                TaskItem.objects.create(title="t", owner=self.owner, project=project)

        _, payload = send.call_args.args
        self.assertIn(tag.id, payload["task"]["tags"])

    def test_ownerless_task_is_not_broadcast(self):
        with mock.patch("tasks.signals.send_to_user") as send:
            with self.captureOnCommitCallbacks(execute=True):
                TaskItem.objects.create(title="orphan", owner=None)

        send.assert_not_called()

    def test_rolled_back_write_is_not_broadcast(self):
        # captureOnCommitCallbacks only runs callbacks for a transaction that commits; a rolled-back
        # block leaves none pending.
        with mock.patch("tasks.signals.send_to_user") as send:
            with self.captureOnCommitCallbacks(execute=True) as callbacks:
                pass
        self.assertEqual(callbacks, [])
        send.assert_not_called()


@override_settings(CHANNEL_LAYERS=IN_MEMORY_LAYER)
class SendToUserResilienceTests(TestCase):
    """A dead channel layer must never turn a task write into a 500."""

    def test_missing_layer_is_a_noop(self):
        with mock.patch("tasks.realtime.get_channel_layer", return_value=None):
            send_to_user(1, {"type": "task.updated", "id": 1})  # must not raise

    def test_layer_failure_is_swallowed(self):
        boom = mock.Mock()
        boom.group_send = mock.Mock(side_effect=RuntimeError("redis down"))
        with mock.patch("tasks.realtime.get_channel_layer", return_value=boom):
            send_to_user(1, {"type": "task.updated", "id": 1})  # must not raise

    def test_write_succeeds_when_broadcast_raises(self):
        owner = User.objects.create_user(username="o", password="pw")
        with mock.patch("tasks.realtime.get_channel_layer", side_effect=RuntimeError("boom")):
            with self.captureOnCommitCallbacks(execute=True):
                task = TaskItem.objects.create(title="t", owner=owner)
        self.assertTrue(TaskItem.objects.filter(pk=task.id).exists())


# Grace is kept comfortably above the sub-second receive_nothing() probes below so the auth-deadline
# close frame never races those assertions.
@override_settings(CHANNEL_LAYERS=IN_MEMORY_LAYER, TASK_WS_AUTH_GRACE_SECONDS=0.5)
class TaskEventsConsumerTests(TransactionTestCase):
    """First-message auth handshake and owner-scoped delivery over a live socket."""

    def setUp(self):
        self.user = User.objects.create_user(username="owner", password="pw")
        self.token = Token.objects.create(user=self.user)
        self.other = User.objects.create_user(username="other", password="pw")
        self.other_token = Token.objects.create(user=self.other)

    async def _connect(self):
        communicator = WebsocketCommunicator(application, "/ws/tasks/")
        connected, _ = await communicator.connect()
        self.assertTrue(connected)
        return communicator

    async def test_valid_token_authenticates(self):
        communicator = await self._connect()
        try:
            await communicator.send_json_to({"type": "auth", "token": self.token.key})
            reply = await communicator.receive_json_from()
            self.assertEqual(reply, {"type": "auth.ok"})
        finally:
            await communicator.disconnect()

    async def test_authenticated_socket_receives_owner_events(self):
        communicator = await self._connect()
        try:
            await communicator.send_json_to({"type": "auth", "token": self.token.key})
            await communicator.receive_json_from()  # auth.ok

            payload = {"type": "task.updated", "id": 7, "task": {"id": 7, "title": "x"}}
            layer = get_channel_layer()
            await layer.group_send(user_group_name(self.user.id), {"type": "task.event", "payload": payload})

            self.assertEqual(await communicator.receive_json_from(), payload)
        finally:
            await communicator.disconnect()

    async def test_events_not_leaked_across_users(self):
        communicator = await self._connect()
        try:
            await communicator.send_json_to({"type": "auth", "token": self.token.key})
            await communicator.receive_json_from()  # auth.ok

            # An event for a different user must never reach this socket.
            layer = get_channel_layer()
            await layer.group_send(
                user_group_name(self.other.id),
                {"type": "task.event", "payload": {"type": "task.updated", "id": 99}},
            )
            self.assertTrue(await communicator.receive_nothing(timeout=0.1))
        finally:
            await communicator.disconnect()

    async def test_no_events_before_auth(self):
        communicator = await self._connect()
        try:
            # Not authenticated → not in any group → an owner event does not arrive.
            layer = get_channel_layer()
            await layer.group_send(
                user_group_name(self.user.id),
                {"type": "task.event", "payload": {"type": "task.updated", "id": 1}},
            )
            self.assertTrue(await communicator.receive_nothing(timeout=0.1))
        finally:
            await communicator.disconnect()

    async def test_invalid_token_is_closed_4401(self):
        communicator = await self._connect()
        try:
            await communicator.send_json_to({"type": "auth", "token": "not-a-real-token"})
            output = await communicator.receive_output(timeout=1)
            self.assertEqual(output["type"], "websocket.close")
            self.assertEqual(output["code"], 4401)
        finally:
            await communicator.disconnect()

    async def test_silent_socket_hits_auth_deadline(self):
        communicator = await self._connect()
        try:
            # Send nothing; the 0.2s grace window elapses and the server closes with 4401.
            output = await communicator.receive_output(timeout=1)
            self.assertEqual(output["type"], "websocket.close")
            self.assertEqual(output["code"], 4401)
        finally:
            await communicator.disconnect()

    async def test_ping_pong_keepalive(self):
        communicator = await self._connect()
        try:
            await communicator.send_json_to({"type": "auth", "token": self.token.key})
            await communicator.receive_json_from()  # auth.ok
            await communicator.send_json_to({"type": "ping"})
            self.assertEqual(await communicator.receive_json_from(), {"type": "pong"})
        finally:
            await communicator.disconnect()
