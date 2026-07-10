"""ASGI-level tests: MCP discovery, the unauthenticated 401 challenge, and Django routing.

Drives the composed ASGI ``application`` (organizer/asgi.py) with Starlette's TestClient, which
runs the MCP session-manager lifespan. The session manager may only be started once per process,
so a single client is opened for the whole class.
"""

from django.conf import settings
from django.test import SimpleTestCase
from starlette.testclient import TestClient

from organizer.asgi import application


class ASGIDiscoveryTests(SimpleTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls._client_ctx = TestClient(application)
        cls.asgi = cls._client_ctx.__enter__()

    @classmethod
    def tearDownClass(cls):
        cls._client_ctx.__exit__(None, None, None)
        super().tearDownClass()

    def test_protected_resource_metadata_is_served_by_mcp_app(self):
        response = self.asgi.get("/.well-known/oauth-protected-resource/mcp")
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertTrue(str(body["resource"]).rstrip("/").endswith("/mcp"))
        self.assertIn(settings.MCP_BASE_URL, [str(a).rstrip("/") for a in body["authorization_servers"]])

    def test_unauthenticated_mcp_request_is_challenged(self):
        response = self.asgi.post(
            "/mcp",
            json={"jsonrpc": "2.0", "id": 1, "method": "tools/list"},
            headers={"Accept": "application/json, text/event-stream"},
        )
        self.assertEqual(response.status_code, 401)
        self.assertIn("WWW-Authenticate", response.headers)

    def test_non_mcp_path_is_routed_to_django(self):
        response = self.asgi.get("/.well-known/oauth-authorization-server")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["issuer"], settings.MCP_BASE_URL)
