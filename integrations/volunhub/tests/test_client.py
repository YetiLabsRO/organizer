"""The HTTP client: path allow-list, refresh, backoff, and all-or-nothing pagination."""

from datetime import timedelta
from unittest import mock

import httpx
from django.test import TestCase, override_settings
from django.utils import timezone

from integrations.volunhub.client import VolunHubAPI
from integrations.volunhub.exceptions import VolunHubAPIError, VolunHubError
from integrations.volunhub.tests.helpers import SETTINGS, make_connection, make_user


@override_settings(**SETTINGS)
class VolunHubAPITests(TestCase):
    def setUp(self):
        self.connection = make_connection(make_user())
        patcher = mock.patch("integrations.volunhub.client.time.sleep")
        patcher.start()
        self.addCleanup(patcher.stop)

    def _api(self, handler):
        return VolunHubAPI(self.connection, client=httpx.Client(transport=httpx.MockTransport(handler)))

    def test_refuses_paths_outside_the_confined_surface(self):
        def handler(request):
            raise AssertionError("no request may be sent")

        with self.assertRaises(VolunHubError):
            self._api(handler).request("GET", "/api/v1/people/profiles/me/")

    def test_sends_bearer_token(self):
        seen = {}

        def handler(request):
            seen["auth"] = request.headers["Authorization"]
            return httpx.Response(200, json={"results": [], "next": None})

        self._api(handler).list_assigned_tasks()
        self.assertEqual(seen["auth"], "Bearer secret-access-token")

    def test_listing_follows_pages_ordered_by_id(self):
        pages = []

        def handler(request):
            page = int(request.url.params["page"])
            pages.append((page, request.url.params["mine"], request.url.params["ordering"]))
            return httpx.Response(200, json={"results": [{"id": page}], "next": "more" if page < 3 else None})

        tasks = self._api(handler).list_assigned_tasks()

        self.assertEqual([task["id"] for task in tasks], [1, 2, 3])
        self.assertEqual(pages, [(1, "true", "id"), (2, "true", "id"), (3, "true", "id")])

    def test_a_failed_page_fails_the_whole_listing(self):
        def handler(request):
            if request.url.params["page"] == "2":
                return httpx.Response(403, json={"detail": "nope"})
            return httpx.Response(200, json={"results": [{"id": 1}], "next": "more"})

        with self.assertRaises(VolunHubAPIError):
            self._api(handler).list_assigned_tasks()

    def test_get_task_returns_none_on_404(self):
        self.assertIsNone(self._api(lambda request: httpx.Response(404)).get_task(5))

    def test_server_errors_are_retried(self):
        responses = iter([httpx.Response(502), httpx.Response(200, json={"results": [], "next": None})])
        self.assertEqual(self._api(lambda request: next(responses)).list_assigned_tasks(), [])

    def test_401_refreshes_once_and_retries(self):
        calls = []

        def handler(request):
            calls.append(request.headers["Authorization"])
            if len(calls) == 1:
                return httpx.Response(401)
            return httpx.Response(200, json={"ok": True})

        def fake_refresh(connection):
            connection.access_token = "fresh-token"

        with mock.patch("integrations.volunhub.client.refresh_access_token", fake_refresh):
            self._api(handler).set_state(9, "planned")

        self.assertEqual(calls, ["Bearer secret-access-token", "Bearer fresh-token"])

    def test_near_expiry_token_is_refreshed_before_the_call(self):
        self.connection.access_token_expires_at = timezone.now() + timedelta(seconds=10)
        refreshed = []

        def fake_refresh(connection):
            refreshed.append(True)
            connection.access_token = "fresh-token"
            connection.access_token_expires_at = timezone.now() + timedelta(hours=1)

        seen = {}

        def handler(request):
            seen["auth"] = request.headers["Authorization"]
            return httpx.Response(200, json={"id": 1})

        with mock.patch("integrations.volunhub.client.refresh_access_token", fake_refresh):
            self._api(handler).get_task(1)

        self.assertEqual(refreshed, [True])
        self.assertEqual(seen["auth"], "Bearer fresh-token")

    def test_patch_sends_only_the_given_fields(self):
        seen = {}

        def handler(request):
            seen["method"], seen["body"] = request.method, request.content
            return httpx.Response(200, json={"id": 4})

        self._api(handler).patch_task(4, {"title": "x"})
        self.assertEqual(seen["method"], "PATCH")
        self.assertEqual(seen["body"], b'{"title":"x"}')
