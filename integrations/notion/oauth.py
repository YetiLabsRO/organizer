"""Organizer as an OAuth 2.0 client of Notion.

Notion's flow differs from the authorization server Organizer itself runs for ``/mcp`` in three
ways that shape this module:

* **No dynamic client registration.** The integration is registered by hand once, and the redirect
  URI must match what was registered there exactly.
* **HTTP Basic client authentication.** The client id and secret go in an ``Authorization`` header
  at the token endpoint, not in the form body.
* **No ``expires_in``.** The token response says nothing about lifetime, so expiry is never
  precomputed — the client refreshes *reactively*, when a call comes back 401 (see client.py).

PKCE is not used: Notion's public-integration flow documents no ``code_challenge`` parameters, and
Organizer is a confidential client holding a real secret. That puts the whole CSRF burden on
``state``, which is why :class:`~integrations.notion.models.NotionOAuthFlow` is single-use and
short-lived.
"""

import logging
import secrets
from urllib.parse import urlencode

import httpx
from django.conf import settings

from integrations.notion.exceptions import NotionAuthError, NotionNotConfigured

logger = logging.getLogger(__name__)

AUTHORIZE_URL = "https://api.notion.com/v1/oauth/authorize"
TOKEN_URL = "https://api.notion.com/v1/oauth/token"

TIMEOUT = httpx.Timeout(30.0)


def is_configured():
    """True when the deployment has a Notion integration registered."""
    return bool(settings.NOTION_CLIENT_ID and settings.NOTION_CLIENT_SECRET)


def _require_configured():
    if not is_configured():
        raise NotionNotConfigured(
            "Notion sync is not configured: set NOTION_CLIENT_ID and NOTION_CLIENT_SECRET "
            "(register a public integration at https://www.notion.so/my-integrations)."
        )


def generate_state():
    """An unguessable, single-use value that is both the CSRF token and the identity carrier."""
    return secrets.token_urlsafe(32)


def build_authorize_url(state):
    """The URL to send the browser to. ``owner=user`` is required by Notion."""
    _require_configured()
    query = urlencode(
        {
            "client_id": settings.NOTION_CLIENT_ID,
            "response_type": "code",
            "owner": "user",
            "redirect_uri": settings.NOTION_REDIRECT_URI,
            "state": state,
        }
    )
    return f"{AUTHORIZE_URL}?{query}"


def _post_token(payload):
    """POST to Notion's token endpoint with HTTP Basic client authentication."""
    _require_configured()
    try:
        response = httpx.post(
            TOKEN_URL,
            json=payload,
            auth=(settings.NOTION_CLIENT_ID, settings.NOTION_CLIENT_SECRET),
            headers={"Notion-Version": settings.NOTION_API_VERSION, "Content-Type": "application/json"},
            timeout=TIMEOUT,
        )
    except httpx.HTTPError as exc:
        raise NotionAuthError(f"Could not reach Notion's token endpoint: {exc}") from exc

    if response.status_code >= 400:
        # Never log the payload — it carries the code or the refresh token.
        try:
            body = response.json()
        except ValueError:
            body = {}
        code = body.get("error", "")
        message = body.get("error_description") or response.text[:200]
        logger.warning("Notion token request failed: %s %s", response.status_code, code)
        raise NotionAuthError(f"Notion rejected the token request ({code or response.status_code}): {message}")

    return response.json()


def exchange_code(code):
    """Trade an authorization code for credentials.

    Returns the raw token response: ``access_token``, ``refresh_token`` (may be absent),
    ``bot_id``, ``workspace_id``, ``workspace_name``, ``workspace_icon``, ``owner``.
    """
    return _post_token(
        {
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": settings.NOTION_REDIRECT_URI,
        }
    )


def refresh_access_token(connection):
    """Refresh ``connection``'s access token in place, persisting the rotated refresh token.

    Notion rotates refresh tokens: each refresh returns a new one and invalidates the old, so
    failing to persist it would break the *next* refresh rather than this one. An ``invalid_grant``
    is terminal — the connection is flipped to ``needs_reauth`` and the caller sees NotionAuthError.
    """
    if not connection.can_refresh:
        connection.mark_needs_reauth("Notion issued no refresh token; reconnect to continue syncing.")
        raise NotionAuthError("No refresh token stored for this connection.")

    try:
        data = _post_token({"grant_type": "refresh_token", "refresh_token": connection.refresh_token})
    except NotionAuthError as exc:
        connection.mark_needs_reauth(str(exc))
        raise

    apply_token_response(connection, data, save=True)
    return connection


def apply_token_response(connection, data, save=False):
    """Copy a token response onto a connection.

    A refresh response may omit ``refresh_token``; when it does, the stored one is kept rather than
    blanked. Everything else is refreshed, since a re-authorization can legitimately land on a
    different workspace.
    """
    connection.access_token = data.get("access_token", "")
    if data.get("refresh_token"):
        connection.refresh_token = data["refresh_token"]

    connection.bot_id = data.get("bot_id") or connection.bot_id
    connection.workspace_id = data.get("workspace_id") or connection.workspace_id
    connection.workspace_name = data.get("workspace_name") or connection.workspace_name
    connection.workspace_icon = data.get("workspace_icon") or connection.workspace_icon or ""

    # A successful exchange clears a previous auth failure, but must not claim the database exists.
    if connection.status == connection.NEEDS_REAUTH or not connection.status:
        connection.status = connection.ACTIVE if getattr(connection, "database", None) else connection.UNPROVISIONED
    connection.last_error = ""

    if save:
        connection.save()
    return connection
