"""The OAuth client: fail-closed registration, PKCE, scope checks and serialized refresh."""

import base64
import hashlib
from unittest import mock
from urllib.parse import parse_qs, urlparse

import httpx
from django.test import TestCase, override_settings

from integrations.volunhub import oauth
from integrations.volunhub.exceptions import VolunHubAPIError, VolunHubAuthError, VolunHubScopeError
from integrations.volunhub.models import VolunHubConnection, VolunHubOAuthClient
from integrations.volunhub.tests.helpers import BASE_URL, REDIRECT_URI, SETTINGS, make_connection, make_user

METADATA = {
    "issuer": BASE_URL,
    "authorization_endpoint": f"{BASE_URL}/authorize",
    "token_endpoint": f"{BASE_URL}/token",
    "registration_endpoint": f"{BASE_URL}/register",
    "revocation_endpoint": f"{BASE_URL}/revoke",
}


def _response(status_code, payload=None):
    return httpx.Response(status_code, json=payload or {}, request=httpx.Request("POST", BASE_URL))


class FakeServer:
    """Routes oauth._send by URL; records what was sent."""

    def __init__(self, registration=None, token=None):
        self.registration = registration or _response(
            201, {"client_id": "registered-id", "scope": "mcp:tasks:read mcp:tasks:write"}
        )
        self.token = token or _response(200, {})
        self.sent = []

    def __call__(self, method, url, **kwargs):
        self.sent.append((method, url, kwargs))
        if url.endswith("/.well-known/oauth-authorization-server"):
            return _response(200, METADATA)
        if url.endswith("/register"):
            return self.registration
        if url.endswith("/token"):
            return self.token
        if url.endswith("/revoke"):
            return _response(200)
        raise AssertionError(f"unexpected {method} {url}")

    def sent_to(self, suffix):
        return [entry for entry in self.sent if entry[1].endswith(suffix)]


@override_settings(**SETTINGS)
class RegistrationTests(TestCase):
    def test_registers_a_confined_public_client_once(self):
        server = FakeServer()
        with mock.patch.object(oauth, "_send", server):
            first = oauth.get_oauth_client()
            second = oauth.get_oauth_client()

        self.assertEqual(first.pk, second.pk)
        self.assertEqual(first.client_id, "registered-id")
        ((_, _, kwargs),) = server.sent_to("/register")
        body = kwargs["json"]
        self.assertEqual(body["token_endpoint_auth_method"], "none")
        self.assertEqual(body["scope"], "mcp:tasks:read mcp:tasks:write")
        self.assertEqual(body["redirect_uris"], [REDIRECT_URI])
        self.assertEqual(set(body["grant_types"]), {"authorization_code", "refresh_token"})

    def test_broader_scope_is_refused_and_not_persisted(self):
        server = FakeServer(registration=_response(201, {"client_id": "x", "scope": "mcp:read mcp:write"}))
        with mock.patch.object(oauth, "_send", server), self.assertRaises(VolunHubScopeError):
            oauth.get_oauth_client()
        self.assertFalse(VolunHubOAuthClient.objects.exists())

    def test_missing_scope_is_refused(self):
        server = FakeServer(registration=_response(201, {"client_id": "x"}))
        with mock.patch.object(oauth, "_send", server), self.assertRaises(VolunHubScopeError):
            oauth.get_oauth_client()

    @override_settings(VOLUNHUB_CLIENT_ID="ops-registered")
    def test_operator_client_id_skips_registration(self):
        server = FakeServer()
        with mock.patch.object(oauth, "_send", server):
            client = oauth.get_oauth_client()
        self.assertEqual(client.client_id, "ops-registered")
        self.assertEqual(server.sent_to("/register"), [])

    def test_metadata_failure_falls_back_to_default_paths(self):
        def unreachable_metadata(method, url, **kwargs):
            if "well-known" in url:
                raise httpx.ConnectError("down")
            return FakeServer()(method, url, **kwargs)

        with mock.patch.object(oauth, "_send", unreachable_metadata):
            client = oauth.get_oauth_client()
        self.assertEqual(client.token_endpoint, f"{BASE_URL}/token")

    @override_settings(VOLUNHUB_REDIRECT_URI="http://localhost:8000/integrations/volunhub/callback/", DEBUG=False)
    def test_local_redirect_uri_is_refused_outside_debug(self):
        from integrations.volunhub.exceptions import VolunHubNotConfigured

        server = FakeServer()
        with mock.patch.object(oauth, "_send", server), self.assertRaises(VolunHubNotConfigured):
            oauth.get_oauth_client()
        self.assertEqual(server.sent, [])
        self.assertFalse(VolunHubOAuthClient.objects.exists())

    @override_settings(VOLUNHUB_REDIRECT_URI="http://localhost:8000/integrations/volunhub/callback/", DEBUG=True)
    def test_local_redirect_uri_is_fine_in_debug(self):
        with mock.patch.object(oauth, "_send", FakeServer()):
            self.assertEqual(oauth.get_oauth_client().client_id, "registered-id")

    @override_settings(VOLUNHUB_BASE_URL="http://volunhub.example.org", DEBUG=False)
    def test_plain_http_is_refused_outside_debug(self):
        from integrations.volunhub.exceptions import VolunHubNotConfigured

        with self.assertRaises(VolunHubNotConfigured):
            oauth.get_oauth_client()


class PkceTests(TestCase):
    def test_challenge_is_s256_of_the_verifier(self):
        verifier = oauth.generate_code_verifier()
        expected = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b"=").decode()
        self.assertEqual(oauth.code_challenge(verifier), expected)
        self.assertTrue(43 <= len(verifier) <= 128)

    @override_settings(**SETTINGS)
    def test_authorize_url_carries_pkce_scope_and_exact_redirect(self):
        client = VolunHubOAuthClient(
            client_id="cid", redirect_uri=REDIRECT_URI, authorization_endpoint=f"{BASE_URL}/authorize"
        )
        query = parse_qs(urlparse(oauth.build_authorize_url(client, "the-state", "v" * 50)).query)
        self.assertEqual(query["client_id"], ["cid"])
        self.assertEqual(query["redirect_uri"], [REDIRECT_URI])
        self.assertEqual(query["scope"], ["mcp:tasks:read mcp:tasks:write"])
        self.assertEqual(query["code_challenge_method"], ["S256"])
        self.assertEqual(query["code_challenge"], [oauth.code_challenge("v" * 50)])
        self.assertEqual(query["state"], ["the-state"])


@override_settings(**SETTINGS)
class TokenTests(TestCase):
    def setUp(self):
        self.connection = make_connection(make_user())

    def test_code_exchange_sends_verifier_and_no_secret(self):
        server = FakeServer(token=_response(200, {"access_token": "at", "scope": "mcp:tasks:read"}))
        with mock.patch.object(oauth, "_send", server):
            oauth.exchange_code(self.connection.client, "the-code", "the-verifier")
        ((_, _, kwargs),) = server.sent_to("/token")
        form = kwargs["data"]
        self.assertEqual(form["code_verifier"], "the-verifier")
        self.assertEqual(form["client_id"], self.connection.client.client_id)
        self.assertNotIn("client_secret", form)

    def test_grant_without_write_is_read_only(self):
        oauth.apply_token_response(self.connection, {"access_token": "at", "scope": "mcp:tasks:read"})
        self.assertFalse(self.connection.can_write)

    def test_grant_without_read_is_rejected(self):
        with self.assertRaises(VolunHubScopeError):
            oauth.apply_token_response(self.connection, {"access_token": "at", "scope": "mcp:tasks:write"})

    def test_refresh_persists_the_rotated_refresh_token(self):
        server = FakeServer(
            token=_response(200, {"access_token": "new-at", "refresh_token": "new-rt", "expires_in": 3600})
        )
        with mock.patch.object(oauth, "_send", server):
            oauth.refresh_access_token(self.connection)

        stored = VolunHubConnection.objects.get(pk=self.connection.pk)
        self.assertEqual(stored.access_token, "new-at")
        self.assertEqual(stored.refresh_token, "new-rt")
        self.assertEqual(self.connection.access_token, "new-at")

    def test_refresh_adopts_a_token_another_worker_already_refreshed(self):
        # Another worker refreshed after we loaded the connection: the row now holds a newer token.
        other_view = VolunHubConnection.objects.get(pk=self.connection.pk)
        other_view.access_token = "refreshed-elsewhere"
        other_view.save()
        server = FakeServer()

        with mock.patch.object(oauth, "_send", server):
            oauth.refresh_access_token(self.connection)

        self.assertEqual(server.sent_to("/token"), [])
        self.assertEqual(self.connection.access_token, "refreshed-elsewhere")

    def test_invalid_grant_marks_needs_reauth(self):
        server = FakeServer(token=_response(400, {"error": "invalid_grant"}))
        with mock.patch.object(oauth, "_send", server), self.assertRaises(VolunHubAuthError):
            oauth.refresh_access_token(self.connection)
        self.connection.refresh_from_db()
        self.assertEqual(self.connection.status, VolunHubConnection.NEEDS_REAUTH)

    def test_server_error_is_transient_not_reauth(self):
        server = FakeServer(token=_response(503))
        with mock.patch.object(oauth, "_send", server), self.assertRaises(VolunHubAPIError):
            oauth.refresh_access_token(self.connection)
        self.connection.refresh_from_db()
        self.assertEqual(self.connection.status, VolunHubConnection.ACTIVE)

    def test_revoke_sends_the_refresh_token_and_client_id(self):
        server = FakeServer()
        with mock.patch.object(oauth, "_send", server):
            self.assertTrue(oauth.revoke(self.connection))
        ((_, _, kwargs),) = server.sent_to("/revoke")
        self.assertEqual(kwargs["data"]["token"], "secret-refresh-token")
        self.assertEqual(kwargs["data"]["client_id"], self.connection.client.client_id)
