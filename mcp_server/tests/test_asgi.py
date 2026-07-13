"""ASGI-level tests: MCP discovery, the unauthenticated 401 challenge, and Django routing.

Drives the composed ASGI ``application`` (organizer/asgi.py) with Starlette's TestClient, which
runs the MCP session-manager lifespan. The session manager may only be started once per process,
so a single client is opened for the whole class.
"""

import asyncio
from urllib.parse import urlparse

from django.conf import settings
from django.test import SimpleTestCase
from mcp.server.transport_security import TransportSecurityMiddleware
from starlette.requests import HTTPConnection
from starlette.testclient import TestClient

from mcp_server.server import mcp
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
        self.assertEqual(response.json()["issuer"].rstrip("/"), settings.MCP_BASE_URL.rstrip("/"))

    def test_as_issuer_matches_protected_resource_authorization_server(self):
        # Regression: strict OAuth clients (Claude) reject discovery unless the AS metadata
        # `issuer` byte-for-byte equals the protected-resource metadata's authorization server.
        prm = self.asgi.get("/.well-known/oauth-protected-resource/mcp").json()
        asm = self.asgi.get("/.well-known/oauth-authorization-server").json()
        self.assertEqual(asm["issuer"], prm["authorization_servers"][0])


class TransportSecurityTests(SimpleTestCase):
    """DNS-rebinding protection must admit the host we are actually reached on.

    Only authenticated requests get this far — the bearer middleware rejects everything else
    first — so the 401 tests above cannot catch a bad allow-list. Left to its own devices FastMCP
    infers the allow-list from its *bind* host (loopback, behind the proxy) and answers every real
    request with 421 "Invalid Host header".
    """

    def _reject_reason(self, host: str):
        connection = HTTPConnection(
            {
                "type": "http",
                "headers": [(b"host", host.encode()), (b"content-type", b"application/json")],
            }
        )
        middleware = TransportSecurityMiddleware(mcp.settings.transport_security)
        response = asyncio.run(middleware.validate_request(connection, is_post=True))
        return None if response is None else response.status_code

    def test_public_host_is_admitted(self):
        self.assertIsNone(self._reject_reason(urlparse(settings.MCP_BASE_URL).netloc))

    def test_foreign_host_is_still_rejected(self):
        # The allow-list is widened to the public host, not disarmed.
        self.assertEqual(self._reject_reason("attacker.example.com"), 421)
