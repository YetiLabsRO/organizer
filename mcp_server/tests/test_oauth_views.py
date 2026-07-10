"""Tests for the RFC 8414 metadata and RFC 7591 dynamic client registration views."""

import json

from django.conf import settings
from django.test import TestCase
from django.urls import reverse
from oauth2_provider.models import get_application_model
from pydantic import AnyHttpUrl

Application = get_application_model()


class AuthorizationServerMetadataTests(TestCase):
    def test_metadata_advertises_endpoints_and_scopes(self):
        response = self.client.get(reverse("oauth_as_metadata"))
        self.assertEqual(response.status_code, 200)
        body = response.json()
        # Issuer must match the normalized form the MCP protected-resource metadata advertises.
        self.assertEqual(body["issuer"], str(AnyHttpUrl(settings.MCP_BASE_URL)))
        self.assertTrue(body["authorization_endpoint"].endswith("/o/authorize/"))
        self.assertTrue(body["token_endpoint"].endswith("/o/token/"))
        self.assertTrue(body["registration_endpoint"].endswith("/o/register/"))
        self.assertEqual(body["code_challenge_methods_supported"], ["S256"])
        self.assertIn("read", body["scopes_supported"])
        self.assertIn("write", body["scopes_supported"])


class DynamicClientRegistrationTests(TestCase):
    def _register(self, payload):
        return self.client.post(
            reverse("oauth_register"),
            data=json.dumps(payload),
            content_type="application/json",
        )

    def test_public_client_registration(self):
        response = self._register(
            {
                "client_name": "Claude",
                "redirect_uris": ["https://claude.ai/api/mcp/auth_callback"],
                "token_endpoint_auth_method": "none",
            }
        )
        self.assertEqual(response.status_code, 201)
        body = response.json()
        self.assertIn("client_id", body)
        self.assertNotIn("client_secret", body)

        app = Application.objects.get(client_id=body["client_id"])
        self.assertEqual(app.client_type, Application.CLIENT_PUBLIC)
        self.assertEqual(app.authorization_grant_type, Application.GRANT_AUTHORIZATION_CODE)

    def test_confidential_client_gets_secret(self):
        response = self._register(
            {
                "client_name": "Backend",
                "redirect_uris": ["https://example.com/callback"],
                "token_endpoint_auth_method": "client_secret_post",
            }
        )
        self.assertEqual(response.status_code, 201)
        body = response.json()
        self.assertIn("client_secret", body)
        app = Application.objects.get(client_id=body["client_id"])
        self.assertEqual(app.client_type, Application.CLIENT_CONFIDENTIAL)

    def test_missing_redirect_uris_is_rejected(self):
        response = self._register({"client_name": "Bad"})
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["error"], "invalid_redirect_uri")

    def test_get_not_allowed(self):
        response = self.client.get(reverse("oauth_register"))
        self.assertEqual(response.status_code, 405)
