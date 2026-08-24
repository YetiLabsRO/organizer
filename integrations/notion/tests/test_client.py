"""The HTTP client: pacing, rate limiting, and refresh-on-401.

Notion never says when an access token expires, so a 401 is the *only* signal the client ever gets.
That path therefore has to work, and has to happen exactly once per call.
"""

from unittest import mock

import httpx
from django.test import TestCase, override_settings

from integrations.notion.client import NotionClient
from integrations.notion.exceptions import NotionAPIError, NotionAuthError, NotionRateLimited
from integrations.notion.models import NotionConnection
from integrations.notion.tests.helpers import make_connection, make_user

SETTINGS = {
    "NOTION_CLIENT_ID": "client-id",
    "NOTION_CLIENT_SECRET": "client-secret",
    "NOTION_API_VERSION": "2025-09-03",
}


@override_settings(**SETTINGS)
class NotionClientTests(TestCase):
    def setUp(self):
        self.connection = make_connection(make_user())
        # Pacing is real behaviour but would make the suite crawl; assert on it separately.
        patcher = mock.patch("integrations.notion.client.time.sleep")
        self.sleep = patcher.start()
        self.addCleanup(patcher.stop)

    def _client(self, handler):
        return NotionClient(self.connection, client=httpx.Client(transport=httpx.MockTransport(handler)))

    def test_sends_the_version_header_and_bearer_token(self):
        seen = {}

        def handler(request):
            seen["version"] = request.headers.get("Notion-Version")
            seen["auth"] = request.headers.get("Authorization")
            return httpx.Response(200, json={"ok": True})

        self._client(handler).request("GET", "/pages/abc")
        self.assertEqual(seen["version"], "2025-09-03")
        self.assertEqual(seen["auth"], "Bearer secret-access-token")

    def test_401_refreshes_once_and_retries(self):
        calls = []

        def handler(request):
            calls.append(request.headers.get("Authorization"))
            if len(calls) == 1:
                return httpx.Response(401, json={"code": "unauthorized"})
            return httpx.Response(200, json={"ok": True})

        def fake_refresh(connection):
            connection.access_token = "refreshed-token"
            connection.save()
            return connection

        with mock.patch("integrations.notion.client.refresh_access_token", side_effect=fake_refresh) as refresh:
            result = self._client(handler).request("GET", "/pages/abc")

        self.assertEqual(result, {"ok": True})
        self.assertEqual(refresh.call_count, 1)
        self.assertEqual(calls[1], "Bearer refreshed-token")

    def test_401_after_refresh_marks_needs_reauth(self):
        def handler(request):
            return httpx.Response(401, json={"code": "unauthorized"})

        with mock.patch("integrations.notion.client.refresh_access_token", side_effect=lambda c: c):
            with self.assertRaises(NotionAuthError):
                self._client(handler).request("GET", "/pages/abc")

        self.connection.refresh_from_db()
        self.assertEqual(self.connection.status, NotionConnection.NEEDS_REAUTH)

    def test_429_waits_for_retry_after_then_succeeds(self):
        calls = []

        def handler(request):
            calls.append(1)
            if len(calls) == 1:
                return httpx.Response(429, headers={"Retry-After": "7"}, json={"code": "rate_limited"})
            return httpx.Response(200, json={"ok": True})

        result = self._client(handler).request("GET", "/pages/abc")

        self.assertEqual(result, {"ok": True})
        # Honoured Notion's own delay rather than a guess of our own.
        self.assertIn(mock.call(7.0), self.sleep.call_args_list)

    def test_persistent_429_raises_rate_limited(self):
        def handler(request):
            return httpx.Response(429, headers={"Retry-After": "1"}, json={"code": "rate_limited"})

        with self.assertRaises(NotionRateLimited):
            self._client(handler).request("GET", "/pages/abc")

    def test_client_error_is_not_retried(self):
        calls = []

        def handler(request):
            calls.append(1)
            return httpx.Response(400, json={"code": "validation_error", "message": "bad property"})

        with self.assertRaises(NotionAPIError) as caught:
            self._client(handler).request("POST", "/pages", json={})

        self.assertEqual(len(calls), 1)
        self.assertEqual(caught.exception.code, "validation_error")

    def test_server_error_is_retried_then_raises(self):
        calls = []

        def handler(request):
            calls.append(1)
            return httpx.Response(502, json={})

        with self.assertRaises(NotionAPIError):
            self._client(handler).request("GET", "/pages/abc")
        self.assertGreater(len(calls), 1)

    def test_pagination_follows_the_cursor(self):
        def handler(request):
            body = request.read().decode()
            if "cursor-2" in body:
                return httpx.Response(200, json={"results": [{"id": "c"}], "has_more": False, "next_cursor": None})
            return httpx.Response(
                200, json={"results": [{"id": "a"}, {"id": "b"}], "has_more": True, "next_cursor": "cursor-2"}
            )

        pages = self._client(handler).query_data_source("ds-1")
        self.assertEqual([page["id"] for page in pages], ["a", "b", "c"])

    def test_query_targets_the_data_source_endpoint(self):
        seen = {}

        def handler(request):
            seen["url"] = str(request.url)
            return httpx.Response(200, json={"results": [], "has_more": False})

        self._client(handler).query_data_source("ds-42")
        # A database id is rejected here; rows live in the data source.
        self.assertIn("/v1/data_sources/ds-42/query", seen["url"])

    def test_trash_page_sends_in_trash(self):
        seen = {}

        def handler(request):
            seen["body"] = request.read().decode()
            return httpx.Response(200, json={"id": "p1", "in_trash": True})

        self._client(handler).trash_page("p1")
        self.assertIn('"in_trash": true', seen["body"].replace('"in_trash":true', '"in_trash": true'))

    def test_paces_requests_below_the_rate_limit(self):
        def handler(request):
            return httpx.Response(200, json={"ok": True})

        client = self._client(handler)
        client.request("GET", "/a")
        client.request("GET", "/b")
        # The second call had to wait; the first did not.
        self.assertTrue(any(call.args and call.args[0] > 0 for call in self.sleep.call_args_list))
