"""The API surface: linking, disconnect, sync-now, project merge, and owner scoping."""

from datetime import timedelta
from unittest import mock

from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone
from rest_framework.test import APIClient

from integrations.volunhub import oauth
from integrations.volunhub.models import (
    VolunHubConnection,
    VolunHubOAuthFlow,
    VolunHubProjectLink,
    VolunHubTaskLink,
)
from integrations.volunhub.tests.helpers import SETTINGS, make_connection, make_oauth_client, make_user
from tasks.models import Project, TaskItem

TOKEN_RESPONSE = {
    "access_token": "at",
    "refresh_token": "rt",
    "expires_in": 3600,
    "scope": "mcp:tasks:read mcp:tasks:write",
}


@override_settings(**SETTINGS)
class AuthenticationRequiredTests(TestCase):
    def test_every_api_endpoint_requires_authentication(self):
        client = APIClient()
        for name, method, kwargs in [
            ("volunhub-api:status", "get", {}),
            ("volunhub-api:connect", "post", {}),
            ("volunhub-api:disconnect", "post", {}),
            ("volunhub-api:sync", "post", {}),
            ("volunhub-api:projects", "get", {}),
            ("volunhub-api:project-merge", "post", {"external_id": 1}),
        ]:
            response = getattr(client, method)(reverse(name, kwargs=kwargs))
            self.assertIn(response.status_code, (401, 403), f"{name} was reachable anonymously")


@override_settings(**SETTINGS)
class LinkingTests(TestCase):
    def setUp(self):
        self.user = make_user()
        self.client = APIClient()
        self.client.force_authenticate(self.user)
        self.oauth_client = make_oauth_client()

    def connect(self):
        with mock.patch.object(oauth, "get_oauth_client", return_value=self.oauth_client):
            return self.client.post(reverse("volunhub-api:connect"))

    def test_connect_records_a_flow_with_a_verifier_and_returns_the_url(self):
        response = self.connect()

        self.assertEqual(response.status_code, 200)
        flow = VolunHubOAuthFlow.objects.get()
        self.assertEqual(flow.user, self.user)
        self.assertIn(flow.state, response.data["authorize_url"])
        self.assertIn(oauth.code_challenge(flow.code_verifier), response.data["authorize_url"])
        self.assertNotIn(flow.code_verifier, response.data["authorize_url"])

    @override_settings(VOLUNHUB_BASE_URL="")
    def test_connect_is_unavailable_when_disabled(self):
        self.assertEqual(self.client.post(reverse("volunhub-api:connect")).status_code, 503)

    def test_callback_links_the_right_user_and_queues_a_sync(self):
        self.connect()
        flow = VolunHubOAuthFlow.objects.get()

        with (
            mock.patch.object(oauth, "exchange_code", return_value=TOKEN_RESPONSE) as exchange,
            mock.patch("integrations.volunhub.views.sync_one") as sync_one,
            self.captureOnCommitCallbacks(execute=True),
        ):
            response = self.client.get(reverse("volunhub:callback"), {"state": flow.state, "code": "c"})

        self.assertEqual(response.status_code, 302)
        self.assertIn("volunhub=connected", response["Location"])
        exchange.assert_called_once_with(self.oauth_client, "c", flow.code_verifier)
        connection = VolunHubConnection.objects.get(user=self.user)
        self.assertEqual(connection.access_token, "at")
        self.assertTrue(connection.can_write)
        sync_one.delay.assert_called_once_with(connection.pk)

    def test_state_is_single_use(self):
        self.connect()
        state = VolunHubOAuthFlow.objects.get().state
        with (
            mock.patch.object(oauth, "exchange_code", return_value=TOKEN_RESPONSE),
            mock.patch("integrations.volunhub.views.sync_one"),
        ):
            self.client.get(reverse("volunhub:callback"), {"state": state, "code": "c"})
            replay = self.client.get(reverse("volunhub:callback"), {"state": state, "code": "c"})
        self.assertIn("reason=invalid_state", replay["Location"])

    def test_expired_state_is_rejected(self):
        self.connect()
        flow = VolunHubOAuthFlow.objects.get()
        VolunHubOAuthFlow.objects.filter(pk=flow.pk).update(created_at=timezone.now() - timedelta(hours=1))
        with mock.patch.object(oauth, "exchange_code") as exchange:
            response = self.client.get(reverse("volunhub:callback"), {"state": flow.state, "code": "c"})
        exchange.assert_not_called()
        self.assertIn("reason=invalid_state", response["Location"])

    def test_error_from_volunhub_is_encoded_into_the_redirect(self):
        response = self.client.get(reverse("volunhub:callback"), {"error": "access_denied&volunhub=connected"})
        self.assertIn("reason=access_denied%26volunhub%3Dconnected", response["Location"])
        self.assertEqual(response["Location"].count("volunhub="), 1)

    def test_grant_without_read_scope_stores_nothing(self):
        self.connect()
        flow = VolunHubOAuthFlow.objects.get()
        with mock.patch.object(oauth, "exchange_code", return_value={**TOKEN_RESPONSE, "scope": "mcp:tasks:write"}):
            response = self.client.get(reverse("volunhub:callback"), {"state": flow.state, "code": "c"})
        self.assertIn("reason=insufficient_scope", response["Location"])
        self.assertFalse(VolunHubConnection.objects.exists())

    def test_status_never_exposes_tokens(self):
        make_connection(self.user)
        response = self.client.get(reverse("volunhub-api:status"))
        self.assertTrue(response.data["connected"])
        self.assertNotIn("secret-access-token", str(response.content))
        self.assertNotIn("secret-refresh-token", str(response.content))


@override_settings(**SETTINGS)
class DisconnectTests(TestCase):
    def setUp(self):
        self.user = make_user()
        self.client = APIClient()
        self.client.force_authenticate(self.user)
        self.connection = make_connection(self.user)
        self.task = TaskItem.objects.create(owner=self.user, title="From VolunHub")
        VolunHubTaskLink.objects.create(user=self.user, external_id=101, task=self.task)

    def test_disconnect_revokes_deletes_credentials_and_keeps_tasks_marked(self):
        with mock.patch.object(oauth, "revoke") as revoke:
            self.client.post(reverse("volunhub-api:disconnect"))

        revoke.assert_called_once()
        self.assertFalse(VolunHubConnection.objects.exists())
        link = VolunHubTaskLink.objects.get()
        self.assertEqual((link.state, link.removed_reason), (VolunHubTaskLink.REMOVED, VolunHubTaskLink.DISCONNECTED))
        self.assertTrue(TaskItem.objects.filter(pk=self.task.pk).exists())


@override_settings(**SETTINGS)
class SyncNowTests(TestCase):
    def setUp(self):
        self.user = make_user()
        self.client = APIClient()
        self.client.force_authenticate(self.user)

    def test_sync_queues_only_the_callers_connection(self):
        connection = make_connection(self.user)
        make_connection(make_user("other"))
        with (
            mock.patch("integrations.volunhub.views.sync_one") as sync_one,
            self.captureOnCommitCallbacks(execute=True),
        ):
            response = self.client.post(reverse("volunhub-api:sync"))
        self.assertEqual(response.data, {"queued": True})
        sync_one.delay.assert_called_once_with(connection.pk)

    def test_retry_content_re_enables_content_push(self):
        connection = make_connection(self.user, content_push_enabled=False)
        with mock.patch("integrations.volunhub.views.sync_one"):
            self.client.post(reverse("volunhub-api:sync"), {"retry_content": True}, format="json")
        connection.refresh_from_db()
        self.assertTrue(connection.content_push_enabled)

    def test_needs_reauth_must_reconnect_first(self):
        make_connection(self.user, status=VolunHubConnection.NEEDS_REAUTH)
        self.assertEqual(self.client.post(reverse("volunhub-api:sync")).status_code, 409)

    def test_no_connection_is_a_400(self):
        self.assertEqual(self.client.post(reverse("volunhub-api:sync")).status_code, 400)


@override_settings(**SETTINGS)
class ProjectMergeTests(TestCase):
    def setUp(self):
        self.user = make_user()
        self.client = APIClient()
        self.client.force_authenticate(self.user)
        self.auto = Project.objects.create(title="Jamboree (VolunHub)")
        self.link = VolunHubProjectLink.objects.create(
            external_id=7, external_name="Jamboree", project=self.auto, auto_created=True
        )
        self.task = TaskItem.objects.create(owner=self.user, title="Tents", project=self.auto)
        VolunHubTaskLink.objects.create(user=self.user, external_id=101, task=self.task, external_project_id=7)
        self.target = Project.objects.create(title="Jamboree")

    def merge(self, project_id, external_id=7):
        return self.client.post(
            reverse("volunhub-api:project-merge", kwargs={"external_id": external_id}),
            {"project_id": project_id},
            format="json",
        )

    def test_projects_lists_links_from_the_callers_tasks(self):
        VolunHubProjectLink.objects.create(external_id=8, external_name="Not mine")
        response = self.client.get(reverse("volunhub-api:projects"))
        self.assertEqual([row["external_id"] for row in response.data], [7])

    def test_merge_moves_tasks_and_deletes_the_empty_auto_created_project(self):
        response = self.merge(self.target.pk)

        self.assertEqual(response.status_code, 200)
        self.task.refresh_from_db()
        self.assertEqual(self.task.project, self.target)
        self.assertFalse(Project.objects.filter(pk=self.auto.pk).exists())
        self.link.refresh_from_db()
        self.assertEqual((self.link.project, self.link.auto_created), (self.target, False))

    def test_remerging_a_real_project_moves_only_volunhub_tasks(self):
        self.merge(self.target.pk)
        own = TaskItem.objects.create(owner=self.user, title="Mine", project=self.target)
        elsewhere = Project.objects.create(title="Elsewhere")

        self.merge(elsewhere.pk)

        self.task.refresh_from_db()
        own.refresh_from_db()
        self.assertEqual(self.task.project, elsewhere)
        self.assertEqual(own.project, self.target)
        self.assertTrue(Project.objects.filter(pk=self.target.pk).exists())

    def test_cannot_merge_a_project_not_linked_to_the_callers_tasks(self):
        VolunHubProjectLink.objects.create(external_id=8, external_name="Someone else's")
        self.assertEqual(self.merge(self.target.pk, external_id=8).status_code, 404)

    def test_unknown_target_is_a_400(self):
        self.assertEqual(self.merge(999999).status_code, 400)


@override_settings(**SETTINGS)
class TaskApiTests(TestCase):
    def test_task_payload_carries_the_volunhub_badge(self):
        user = make_user()
        client = APIClient()
        client.force_authenticate(user)
        task = TaskItem.objects.create(owner=user, title="Linked")
        VolunHubTaskLink.objects.create(
            user=user,
            external_id=55,
            task=task,
            state=VolunHubTaskLink.REMOVED,
            removed_reason=VolunHubTaskLink.UNASSIGNED,
        )
        TaskItem.objects.create(owner=user, title="Plain")

        rows = {row["title"]: row for row in client.get("/api/task/").data["results"]}

        self.assertEqual(
            rows["Linked"]["volunhub"],
            {
                "url": "https://volunhub.example.org/proiecte/task-uri/55/",
                "state": "removed",
                "removed_reason": "unassigned",
                "error": None,
            },
        )
        self.assertIsNone(rows["Plain"]["volunhub"])
        detail = client.get(f"/api/task/{task.pk}/").data
        self.assertEqual(detail["volunhub"]["state"], "removed")
