"""Tests for the OAuth token verifier and the per-tool write-scope guard."""

from datetime import timedelta

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone
from mcp.server.auth.middleware.auth_context import auth_context_var
from mcp.server.auth.middleware.bearer_auth import AuthenticatedUser
from mcp.server.auth.provider import AccessToken as MCPAccessToken
from mcp.server.fastmcp.exceptions import ToolError
from oauth2_provider.models import get_access_token_model, get_application_model

from mcp_server import tools
from mcp_server.auth import DjangoOAuthTokenVerifier

User = get_user_model()
Application = get_application_model()
AccessToken = get_access_token_model()


class TokenVerifierTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user("owner", password="pw")
        self.app = Application.objects.create(
            name="MCP client",
            client_type=Application.CLIENT_PUBLIC,
            authorization_grant_type=Application.GRANT_AUTHORIZATION_CODE,
            redirect_uris="http://localhost/callback",
        )
        self.verifier = DjangoOAuthTokenVerifier()

    def _make_token(self, *, token="tok", scope="read write", user=True, expired=False):
        return AccessToken.objects.create(
            user=self.user if user else None,
            token=token,
            application=self.app,
            scope=scope,
            expires=timezone.now() + timedelta(hours=-1 if expired else 1),
        )

    def test_valid_token_resolves_user(self):
        self._make_token(token="good")
        info = self.verifier._verify("good")
        self.assertIsNotNone(info)
        self.assertEqual(info.subject, str(self.user.id))
        self.assertEqual(sorted(info.scopes), ["read", "write"])
        self.assertEqual(info.claims["username"], "owner")

    def test_unknown_token_is_rejected(self):
        self.assertIsNone(self.verifier._verify("nope"))

    def test_expired_token_is_rejected(self):
        self._make_token(token="old", expired=True)
        self.assertIsNone(self.verifier._verify("old"))

    def test_userless_token_is_rejected(self):
        self._make_token(token="orphan", user=False)
        self.assertIsNone(self.verifier._verify("orphan"))


class WriteScopeGuardTests(TestCase):
    def _set_token(self, scopes):
        token = MCPAccessToken(token="x", client_id="c", scopes=scopes, subject="42")
        return auth_context_var.set(AuthenticatedUser(token))

    def test_user_id_from_subject(self):
        reset = self._set_token(["read", "write"])
        try:
            self.assertEqual(tools._user_id(), 42)
        finally:
            auth_context_var.reset(reset)

    def test_write_requires_write_scope(self):
        reset = self._set_token(["read"])
        try:
            with self.assertRaises(ToolError):
                tools._writer_id()
        finally:
            auth_context_var.reset(reset)

    def test_write_allowed_with_write_scope(self):
        reset = self._set_token(["read", "write"])
        try:
            self.assertEqual(tools._writer_id(), 42)
        finally:
            auth_context_var.reset(reset)

    def test_missing_token_is_rejected(self):
        with self.assertRaises(ToolError):
            tools._user_id()
