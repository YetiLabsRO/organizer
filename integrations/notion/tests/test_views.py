"""The API surface: linking, provisioning, and owner scoping.

The callback is the interesting one — it is the only unauthenticated endpoint here, because the
browser navigation Notion sends back carries no DRF token. Everything it does hangs off ``state``.
"""

from datetime import timedelta
from unittest import mock

from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone
from rest_framework.test import APIClient

from integrations.notion.exceptions import NotionAuthError
from integrations.notion.models import NotionConnection, NotionDatabase, NotionOAuthFlow
from integrations.notion.tests.helpers import make_connection, make_database, make_fake, make_user

SETTINGS = {
    "NOTION_CLIENT_ID": "client-id",
    "NOTION_CLIENT_SECRET": "client-secret",
    "NOTION_REDIRECT_URI": "https://organizer.example.com/integrations/notion/callback/",
    "FRONTEND_BASE_URL": "https://app.example.com",
}

TOKEN_RESPONSE = {
    "access_token": "at",
    "refresh_token": "rt",
    "bot_id": "bot-1",
    "workspace_id": "ws-1",
    "workspace_name": "My workspace",
}


@override_settings(**SETTINGS)
class AuthenticationRequiredTests(TestCase):
    def test_every_api_endpoint_requires_authentication(self):
        client = APIClient()
        for name, method in [
            ("notion-api:status", "get"),
            ("notion-api:connect", "post"),
            ("notion-api:disconnect", "post"),
            ("notion-api:pages", "get"),
            ("notion-api:provision", "post"),
            ("notion-api:sync", "post"),
        ]:
            response = getattr(client, method)(reverse(name))
            self.assertIn(response.status_code, (401, 403), f"{name} was reachable anonymously")


@override_settings(**SETTINGS)
class ConnectTests(TestCase):
    def setUp(self):
        self.user = make_user()
        self.client = APIClient()
        self.client.force_authenticate(self.user)

    def test_connect_records_a_pending_flow_and_returns_the_url(self):
        response = self.client.post(reverse("notion-api:connect"))

        self.assertEqual(response.status_code, 200)
        flow = NotionOAuthFlow.objects.get()
        self.assertEqual(flow.user, self.user)
        self.assertIn(flow.state, response.data["authorize_url"])
        self.assertIn("owner=user", response.data["authorize_url"])

    @override_settings(NOTION_CLIENT_ID="", NOTION_CLIENT_SECRET="")
    def test_connect_is_unavailable_when_the_server_is_not_configured(self):
        response = self.client.post(reverse("notion-api:connect"))
        self.assertEqual(response.status_code, 503)

    def test_connect_purges_expired_flows(self):
        stale = NotionOAuthFlow.objects.create(state="stale", user=self.user)
        NotionOAuthFlow.objects.filter(pk=stale.pk).update(created_at=timezone.now() - timedelta(hours=2))

        self.client.post(reverse("notion-api:connect"))

        self.assertFalse(NotionOAuthFlow.objects.filter(pk=stale.pk).exists())


@override_settings(**SETTINGS)
class CallbackTests(TestCase):
    def setUp(self):
        self.user = make_user()
        self.url = reverse("notion:callback")

    def _flow(self, user=None):
        return NotionOAuthFlow.objects.create(state="state-value", user=user or self.user)

    def test_callback_binds_the_tokens_to_the_user_from_state(self):
        self._flow()

        with mock.patch("integrations.notion.views.oauth.exchange_code", return_value=TOKEN_RESPONSE):
            response = self.client.get(self.url, {"code": "the-code", "state": "state-value"})

        self.assertEqual(response.status_code, 302)
        self.assertIn("notion=connected", response.url)
        connection = NotionConnection.objects.get()
        self.assertEqual(connection.user, self.user)
        self.assertEqual(connection.access_token, "at")
        self.assertEqual(connection.bot_id, "bot-1")

    def test_state_binds_to_the_right_user_among_several(self):
        other = make_user("other")
        NotionOAuthFlow.objects.create(state="other-state", user=other)
        self._flow()

        with mock.patch("integrations.notion.views.oauth.exchange_code", return_value=TOKEN_RESPONSE):
            self.client.get(self.url, {"code": "c", "state": "other-state"})

        self.assertEqual(NotionConnection.objects.get().user, other)

    def test_unknown_state_is_rejected(self):
        with mock.patch("integrations.notion.views.oauth.exchange_code") as exchange:
            response = self.client.get(self.url, {"code": "c", "state": "never-issued"})

        exchange.assert_not_called()
        self.assertIn("invalid_state", response.url)
        self.assertEqual(NotionConnection.objects.count(), 0)

    def test_expired_state_is_rejected(self):
        flow = self._flow()
        NotionOAuthFlow.objects.filter(pk=flow.pk).update(created_at=timezone.now() - timedelta(hours=1))

        with mock.patch("integrations.notion.views.oauth.exchange_code") as exchange:
            response = self.client.get(self.url, {"code": "c", "state": "state-value"})

        exchange.assert_not_called()
        self.assertIn("invalid_state", response.url)

    def test_replayed_state_is_rejected(self):
        self._flow()

        with mock.patch("integrations.notion.views.oauth.exchange_code", return_value=TOKEN_RESPONSE):
            self.client.get(self.url, {"code": "c", "state": "state-value"})
            # Single-use: the second attempt with the same state must not issue credentials again.
            response = self.client.get(self.url, {"code": "c", "state": "state-value"})

        self.assertIn("invalid_state", response.url)
        self.assertEqual(NotionConnection.objects.count(), 1)

    def test_user_denial_redirects_with_the_reason(self):
        response = self.client.get(self.url, {"error": "access_denied", "state": "state-value"})

        self.assertIn("notion=error", response.url)
        self.assertIn("access_denied", response.url)

    def test_a_failed_exchange_does_not_create_a_connection(self):
        self._flow()

        with mock.patch("integrations.notion.views.oauth.exchange_code", side_effect=NotionAuthError("nope")):
            response = self.client.get(self.url, {"code": "c", "state": "state-value"})

        self.assertIn("exchange_failed", response.url)
        self.assertEqual(NotionConnection.objects.count(), 0)

    def test_missing_code_is_rejected(self):
        self._flow()
        response = self.client.get(self.url, {"state": "state-value"})
        self.assertIn("missing_code", response.url)


@override_settings(**SETTINGS)
class StatusAndDisconnectTests(TestCase):
    def setUp(self):
        self.user = make_user()
        self.client = APIClient()
        self.client.force_authenticate(self.user)

    def test_status_reports_disconnected_when_there_is_no_connection(self):
        response = self.client.get(reverse("notion-api:status"))

        self.assertFalse(response.data["connected"])
        self.assertTrue(response.data["configured"])

    def test_status_never_exposes_tokens(self):
        make_connection(self.user)

        response = self.client.get(reverse("notion-api:status"))

        body = str(response.data)
        self.assertNotIn("secret-access-token", body)
        self.assertNotIn("secret-refresh-token", body)
        self.assertNotIn("access_token", response.data)

    def test_status_is_scoped_to_the_requesting_user(self):
        other = make_user("other")
        make_connection(other)

        response = self.client.get(reverse("notion-api:status"))

        self.assertFalse(response.data["connected"])

    def test_status_reports_provisioning_and_bootstrap_progress(self):
        connection = make_connection(self.user)
        make_database(connection)

        response = self.client.get(reverse("notion-api:status"))

        self.assertTrue(response.data["provisioned"])
        self.assertEqual(response.data["bootstrap_state"], NotionDatabase.BOOTSTRAP_DONE)
        # Notion accepts the dashless id in a URL; real ids are dashed UUIDs.
        self.assertEqual(response.data["database_url"], "https://www.notion.so/db1")

    def test_disconnect_destroys_the_credentials(self):
        make_connection(self.user)

        response = self.client.post(reverse("notion-api:disconnect"))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(NotionConnection.objects.count(), 0)

    def test_disconnect_only_affects_the_caller(self):
        other = make_user("other")
        make_connection(other)
        make_connection(self.user)

        self.client.post(reverse("notion-api:disconnect"))

        self.assertEqual(NotionConnection.objects.get().user, other)


@override_settings(**SETTINGS)
class ProvisionTests(TestCase):
    def setUp(self):
        self.user = make_user()
        self.connection = make_connection(self.user)
        self.client = APIClient()
        self.client.force_authenticate(self.user)
        self.fake = make_fake()

    def _provision(self, **payload):
        payload.setdefault("parent_page_id", "parent-page")
        with mock.patch("integrations.notion.views.NotionClient", return_value=self.fake):
            with mock.patch("integrations.notion.views.bootstrap_connection.delay") as enqueued:
                response = self.client.post(reverse("notion-api:provision"), payload)
        return response, enqueued

    def test_provisioning_creates_the_database_and_enqueues_the_bootstrap(self):
        response, enqueued = self._provision()

        self.assertEqual(response.status_code, 200)
        database = NotionDatabase.objects.get()
        self.assertEqual(database.connection, self.connection)
        self.assertEqual(database.parent_page_id, "parent-page")
        # The upload is paced at ~3 requests/second, so it must never run inline in the request.
        enqueued.assert_called_once_with(self.connection.pk)

    def test_provisioning_twice_is_refused(self):
        self._provision()

        response, _ = self._provision()

        self.assertEqual(response.status_code, 409)
        self.assertEqual(NotionDatabase.objects.count(), 1)

    def test_provisioning_requires_a_connection(self):
        self.connection.delete()

        response, _ = self._provision()

        self.assertEqual(response.status_code, 400)

    def test_parent_page_id_is_required(self):
        with mock.patch("integrations.notion.views.NotionClient", return_value=self.fake):
            response = self.client.post(reverse("notion-api:provision"), {})

        self.assertEqual(response.status_code, 400)

    def test_pages_endpoint_lists_shareable_parents(self):
        with mock.patch("integrations.notion.views.NotionClient", return_value=self.fake):
            response = self.client.get(reverse("notion-api:pages"))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data[0]["id"], "parent-page")


@override_settings(**SETTINGS)
class SyncEndpointTests(TestCase):
    def setUp(self):
        self.user = make_user()
        self.connection = make_connection(self.user)
        self.client = APIClient()
        self.client.force_authenticate(self.user)

    def test_sync_enqueues_for_the_caller_only(self):
        make_database(self.connection)

        with mock.patch("integrations.notion.views.sync_one.delay") as enqueued:
            response = self.client.post(reverse("notion-api:sync"))

        self.assertEqual(response.status_code, 200)
        enqueued.assert_called_once_with(self.connection.pk, full=False)

    def test_sync_requires_a_provisioned_database(self):
        with mock.patch("integrations.notion.views.sync_one.delay") as enqueued:
            response = self.client.post(reverse("notion-api:sync"))

        self.assertEqual(response.status_code, 400)
        enqueued.assert_not_called()
