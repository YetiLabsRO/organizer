"""Shared fixtures for the VolunHub integration tests."""

from datetime import timedelta

from django.contrib.auth import get_user_model
from django.utils import timezone

from integrations.volunhub.models import REQUESTED_SCOPES, VolunHubConnection, VolunHubOAuthClient

BASE_URL = "https://volunhub.example.org"
REDIRECT_URI = "https://organizer.example.com/integrations/volunhub/callback/"
FULL_SCOPE = " ".join(REQUESTED_SCOPES)

SETTINGS = {
    "VOLUNHUB_BASE_URL": BASE_URL,
    "VOLUNHUB_REDIRECT_URI": REDIRECT_URI,
    "VOLUNHUB_CLIENT_ID": "",
    "FRONTEND_BASE_URL": "https://app.example.com",
}


def make_user(username="tester", **kwargs):
    return get_user_model().objects.create_user(username=username, password="hunter2-not-a-real-password", **kwargs)


def make_oauth_client(client_id="client-123"):
    return VolunHubOAuthClient.objects.create(
        base_url=BASE_URL,
        redirect_uri=REDIRECT_URI,
        client_id=client_id,
        scope=" ".join(REQUESTED_SCOPES),
        authorization_endpoint=f"{BASE_URL}/authorize",
        token_endpoint=f"{BASE_URL}/token",
        revocation_endpoint=f"{BASE_URL}/revoke",
    )


def make_connection(user, *, client=None, scope=FULL_SCOPE, expires_in=3600, **kwargs):
    connection = VolunHubConnection(
        user=user,
        client=client or VolunHubOAuthClient.objects.first() or make_oauth_client(),
        granted_scope=scope,
        access_token_expires_at=timezone.now() + timedelta(seconds=expires_in),
        **kwargs,
    )
    connection.access_token = "secret-access-token"
    connection.refresh_token = "secret-refresh-token"
    connection.save()
    return connection
