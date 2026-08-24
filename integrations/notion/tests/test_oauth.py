"""The OAuth client: URL construction, HTTP Basic exchange, and rotating refresh tokens."""

from unittest import mock
from urllib.parse import parse_qs, urlparse

import httpx
from django.test import TestCase, override_settings

from integrations.notion import oauth
from integrations.notion.exceptions import NotionAuthError, NotionNotConfigured
from integrations.notion.models import NotionConnection
from integrations.notion.tests.helpers import make_connection, make_user

SETTINGS = {
    "NOTION_CLIENT_ID": "client-id",
    "NOTION_CLIENT_SECRET": "client-secret",
    "NOTION_REDIRECT_URI": "https://organizer.example.com/integrations/notion/callback/",
}


def _response(status_code, payload):
    return httpx.Response(status_code, json=payload, request=httpx.Request("POST", oauth.TOKEN_URL))


@override_settings(**SETTINGS)
class AuthorizeUrlTests(TestCase):
    def test_carries_the_parameters_notion_requires(self):
        url = oauth.build_authorize_url("state-value")
        query = parse_qs(urlparse(url).query)

        self.assertEqual(query["response_type"], ["code"])
        # Notion rejects the flow without owner=user.
        self.assertEqual(query["owner"], ["user"])
        self.assertEqual(query["client_id"], ["client-id"])
        self.assertEqual(query["state"], ["state-value"])
        # Must match the registered URI exactly, trailing slash included.
        self.assertEqual(query["redirect_uri"], [SETTINGS["NOTION_REDIRECT_URI"]])

    def test_state_is_unguessable_and_unique(self):
        states = {oauth.generate_state() for _ in range(100)}
        self.assertEqual(len(states), 100)
        self.assertTrue(all(len(state) >= 32 for state in states))


class NotConfiguredTests(TestCase):
    @override_settings(NOTION_CLIENT_ID="", NOTION_CLIENT_SECRET="")
    def test_authorize_url_refuses_without_credentials(self):
        self.assertFalse(oauth.is_configured())
        with self.assertRaises(NotionNotConfigured):
            oauth.build_authorize_url("state")


@override_settings(**SETTINGS)
class ExchangeTests(TestCase):
    def test_uses_http_basic_client_authentication(self):
        payload = {"access_token": "at", "refresh_token": "rt", "bot_id": "bot", "workspace_id": "ws"}
        with mock.patch("integrations.notion.oauth.httpx.post", return_value=_response(200, payload)) as post:
            data = oauth.exchange_code("the-code")

        self.assertEqual(data["access_token"], "at")
        kwargs = post.call_args.kwargs
        # Notion authenticates the client with Basic auth, not client_secret_post.
        self.assertEqual(kwargs["auth"], ("client-id", "client-secret"))
        self.assertEqual(kwargs["json"]["grant_type"], "authorization_code")
        self.assertEqual(kwargs["json"]["code"], "the-code")
        self.assertNotIn("client_secret", kwargs["json"])

    def test_rejection_raises_auth_error(self):
        body = {"error": "invalid_grant", "error_description": "code expired"}
        with mock.patch("integrations.notion.oauth.httpx.post", return_value=_response(400, body)):
            with self.assertRaises(NotionAuthError):
                oauth.exchange_code("stale")


@override_settings(**SETTINGS)
class RefreshTests(TestCase):
    def setUp(self):
        self.connection = make_connection(make_user())

    def test_rotated_refresh_token_is_persisted(self):
        # Notion rotates refresh tokens: dropping the new one breaks the *next* refresh, not this one.
        payload = {"access_token": "new-access", "refresh_token": "new-refresh"}
        with mock.patch("integrations.notion.oauth.httpx.post", return_value=_response(200, payload)):
            oauth.refresh_access_token(self.connection)

        self.connection.refresh_from_db()
        self.assertEqual(self.connection.access_token, "new-access")
        self.assertEqual(self.connection.refresh_token, "new-refresh")

    def test_refresh_without_a_new_token_keeps_the_stored_one(self):
        with mock.patch("integrations.notion.oauth.httpx.post", return_value=_response(200, {"access_token": "a2"})):
            oauth.refresh_access_token(self.connection)

        self.connection.refresh_from_db()
        self.assertEqual(self.connection.refresh_token, "secret-refresh-token")

    def test_invalid_grant_marks_the_connection_for_reauthorization(self):
        body = {"error": "invalid_grant", "error_description": "refresh token is invalid"}
        with mock.patch("integrations.notion.oauth.httpx.post", return_value=_response(400, body)):
            with self.assertRaises(NotionAuthError):
                oauth.refresh_access_token(self.connection)

        self.connection.refresh_from_db()
        self.assertEqual(self.connection.status, NotionConnection.NEEDS_REAUTH)

    def test_connection_without_refresh_token_needs_reauth(self):
        self.connection.refresh_token_encrypted = ""
        self.connection.save()
        with self.assertRaises(NotionAuthError):
            oauth.refresh_access_token(self.connection)
        self.connection.refresh_from_db()
        self.assertEqual(self.connection.status, NotionConnection.NEEDS_REAUTH)


class TokenStorageTests(TestCase):
    def test_tokens_are_encrypted_at_rest(self):
        connection = make_connection(make_user())
        connection.refresh_from_db()

        self.assertEqual(connection.access_token, "secret-access-token")
        # The stored column must not contain the plaintext.
        self.assertNotIn("secret-access-token", connection.access_token_encrypted)
        self.assertTrue(connection.access_token_encrypted)
