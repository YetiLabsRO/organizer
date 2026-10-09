"""Organizer as an OAuth 2.1 public client of VolunHub.

VolunHub's authorization server differs from Notion's in ways that shape this module:

* **Dynamic client registration (RFC 7591).** Organizer registers *itself* — once per deployment and
  redirect URI, never per user — and keeps the ``client_id``. The scope requested at registration
  is what confines the client: exactly ``mcp:tasks:read mcp:tasks:write`` pins it to the tasks and
  projects endpoints, while anything broader yields a full-scope client. So registration fails
  closed unless VolunHub hands back exactly that set.
* **Public client + PKCE (S256).** No secret exists; the ``code_verifier`` proves the callback
  belongs to the flow we started.
* **Rotating refresh tokens with no reuse grace.** Each refresh revokes the previous refresh token,
  so two workers refreshing concurrently would make the loser look like a revoked grant. Refreshes
  are therefore serialized on the connection row (:func:`refresh_access_token`).
* **Consent can narrow scope.** The user may untick the write permission, so every token response's
  ``scope`` is checked: no read means no link, no write means a read-only connection.
"""

import base64
import hashlib
import logging
import secrets
from datetime import timedelta
from urllib.parse import urlencode, urlparse

import httpx
from django.conf import settings
from django.db import transaction
from django.utils import timezone

from integrations.volunhub.exceptions import (
    VolunHubAPIError,
    VolunHubAuthError,
    VolunHubNotConfigured,
    VolunHubScopeError,
)
from integrations.volunhub.locks import lock_registration
from integrations.volunhub.models import (
    REQUESTED_SCOPES,
    SCOPE_READ,
    VolunHubConnection,
    VolunHubOAuthClient,
    scope_set,
)

logger = logging.getLogger(__name__)

TIMEOUT = httpx.Timeout(30.0, connect=10.0)
METADATA_PATH = "/.well-known/oauth-authorization-server"
# Used when the metadata document cannot be fetched. These are VolunHub's documented paths.
DEFAULT_ENDPOINTS = {
    "authorization_endpoint": "/authorize",
    "token_endpoint": "/token",
    "registration_endpoint": "/register",
    "revocation_endpoint": "/revoke",
}
CLIENT_NAME = "Organizer"
# Access tokens live ~1h; when VolunHub omits expires_in, assume that.
DEFAULT_EXPIRES_IN = 3600
# OAuth error codes that mean the grant is gone for good — only the user can fix it.
TERMINAL_ERRORS = {"invalid_grant", "invalid_client", "unauthorized_client", "invalid_scope", "access_denied"}


def is_configured():
    return bool(settings.VOLUNHUB_BASE_URL and settings.VOLUNHUB_REDIRECT_URI)


def _require_configured():
    if not is_configured():
        raise VolunHubNotConfigured("VolunHub sync is disabled: set VOLUNHUB_BASE_URL and VOLUNHUB_REDIRECT_URI.")
    if not settings.DEBUG and not settings.VOLUNHUB_BASE_URL.startswith("https://"):
        raise VolunHubNotConfigured("VOLUNHUB_BASE_URL must use https outside DEBUG — it carries bearer tokens.")
    if not settings.DEBUG and _is_local(settings.VOLUNHUB_REDIRECT_URI):
        # Registering this would send every user back to their own machine after consenting in
        # VolunHub — fail at connect time instead, with the fix in the message.
        raise VolunHubNotConfigured(
            f"VOLUNHUB_REDIRECT_URI is {settings.VOLUNHUB_REDIRECT_URI!r}, which VolunHub cannot send users back "
            "to. Set it (or MCP_BASE_URL) to this server's public URL."
        )


def _is_local(url):
    host = (urlparse(url).hostname or "").lower()
    return host in ("localhost", "127.0.0.1", "::1", "0.0.0.0") or host.endswith(".localhost")


def _send(method, url, **kwargs):
    """The one place this module touches the network, so tests have a single seam to replace."""
    return httpx.request(method, url, timeout=TIMEOUT, **kwargs)


def _json_or_empty(response):
    try:
        data = response.json()
    except ValueError:
        return {}
    return data if isinstance(data, dict) else {}


# --------------------------------------------------------------------------------------
# Discovery + registration
# --------------------------------------------------------------------------------------
def discover(base_url):
    """Absolute OAuth endpoints, from RFC 8414 metadata where available, else the defaults.

    VolunHub's metadata lists only ``client_secret_*`` under ``token_endpoint_auth_methods_supported``
    although public clients work, so that list is deliberately not validated.
    """
    endpoints = {key: f"{base_url}{path}" for key, path in DEFAULT_ENDPOINTS.items()}
    try:
        response = _send("GET", f"{base_url}{METADATA_PATH}")
        if response.status_code == 200:
            metadata = _json_or_empty(response)
            for key in endpoints:
                if metadata.get(key):
                    endpoints[key] = metadata[key]
        else:
            logger.info("VolunHub metadata returned %s; using default endpoints", response.status_code)
    except httpx.HTTPError as exc:
        logger.info("VolunHub metadata unreachable (%s); using default endpoints", exc)
    return endpoints


def register(registration_endpoint, redirect_uri):
    """RFC 7591 registration of this deployment as a confined public client. Returns ``(id, scope)``."""
    payload = {
        "client_name": CLIENT_NAME,
        "redirect_uris": [redirect_uri],
        "token_endpoint_auth_method": "none",
        "grant_types": ["authorization_code", "refresh_token"],
        "response_types": ["code"],
        "scope": " ".join(REQUESTED_SCOPES),
    }
    try:
        response = _send("POST", registration_endpoint, json=payload)
    except httpx.HTTPError as exc:
        raise VolunHubAPIError(f"Could not reach VolunHub to register: {exc}") from exc
    data = _json_or_empty(response)
    if response.status_code >= 400 or not data.get("client_id"):
        raise VolunHubAPIError(
            f"VolunHub refused the client registration ({response.status_code}): "
            f"{data.get('error_description') or data.get('error') or response.text[:200]}",
            status_code=response.status_code,
            body=data,
        )
    # Fail closed: a missing or broader scope means an unconfined client. Never persist it.
    if scope_set(data.get("scope")) != set(REQUESTED_SCOPES):
        raise VolunHubScopeError(
            f"VolunHub registered the client with scope {data.get('scope')!r} instead of exactly "
            f"{' '.join(REQUESTED_SCOPES)!r}; refusing to use an unconfined client."
        )
    return data["client_id"], data["scope"]


def get_oauth_client():
    """The deployment's registered client for the configured base URL and redirect URI.

    Registers lazily on first use, under an advisory lock so two concurrent first connects do not
    each create a client record in VolunHub.
    """
    _require_configured()
    base_url, redirect_uri = settings.VOLUNHUB_BASE_URL, settings.VOLUNHUB_REDIRECT_URI
    override = settings.VOLUNHUB_CLIENT_ID

    def usable(row):
        return row is not None and (not override or row.client_id == override)

    row = VolunHubOAuthClient.objects.filter(base_url=base_url, redirect_uri=redirect_uri).first()
    if usable(row):
        return row

    with transaction.atomic():
        lock_registration()
        row = VolunHubOAuthClient.objects.filter(base_url=base_url, redirect_uri=redirect_uri).first()
        if usable(row):
            return row
        endpoints = discover(base_url)
        if override:
            client_id, scope = override, " ".join(REQUESTED_SCOPES)
        else:
            client_id, scope = register(endpoints["registration_endpoint"], redirect_uri)
            logger.info("Registered VolunHub OAuth client %s for %s", client_id, redirect_uri)
        values = {
            "client_id": client_id,
            "scope": scope,
            "authorization_endpoint": endpoints["authorization_endpoint"],
            "token_endpoint": endpoints["token_endpoint"],
            "revocation_endpoint": endpoints["revocation_endpoint"] or "",
        }
        row, _ = VolunHubOAuthClient.objects.update_or_create(
            base_url=base_url, redirect_uri=redirect_uri, defaults=values
        )
    return row


# --------------------------------------------------------------------------------------
# Authorization code + PKCE
# --------------------------------------------------------------------------------------
def generate_state():
    """An unguessable, single-use value that is both the CSRF token and the identity carrier."""
    return secrets.token_urlsafe(32)


def generate_code_verifier():
    """RFC 7636: 43–128 characters from the unreserved set. token_urlsafe(64) gives 86."""
    return secrets.token_urlsafe(64)


def code_challenge(verifier):
    """S256: base64url(SHA-256(verifier)) without padding."""
    digest = hashlib.sha256(verifier.encode("ascii")).digest()
    return base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")


def build_authorize_url(client, state, verifier):
    query = urlencode(
        {
            "response_type": "code",
            "client_id": client.client_id,
            "redirect_uri": client.redirect_uri,
            "scope": " ".join(REQUESTED_SCOPES),
            "code_challenge": code_challenge(verifier),
            "code_challenge_method": "S256",
            "state": state,
        }
    )
    return f"{client.authorization_endpoint}?{query}"


def _post_token(client, form):
    """POST to the token endpoint as a public client: ``client_id`` in the form, never a secret."""
    try:
        response = _send("POST", client.token_endpoint, data={**form, "client_id": client.client_id})
    except httpx.HTTPError as exc:
        raise VolunHubAPIError(f"Could not reach VolunHub's token endpoint: {exc}") from exc

    data = _json_or_empty(response)
    if response.status_code >= 500:
        raise VolunHubAPIError(
            f"VolunHub's token endpoint is unavailable ({response.status_code}).", response.status_code
        )
    if response.status_code >= 400:
        # Never log the form — it carries the code, the verifier or the refresh token.
        code = data.get("error", "")
        logger.warning("VolunHub token request failed: %s %s", response.status_code, code)
        raise VolunHubAuthError(
            f"VolunHub rejected the token request ({code or response.status_code}): "
            f"{data.get('error_description') or response.text[:200]}"
        )
    if not data.get("access_token"):
        raise VolunHubAuthError("VolunHub's token response carried no access token.")
    return data


def exchange_code(client, code, verifier):
    return _post_token(
        client,
        {
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": client.redirect_uri,
            "code_verifier": verifier,
        },
    )


def apply_token_response(connection, data):
    """Copy a token response onto ``connection`` (unsaved).

    Raises VolunHubScopeError when the grant lacks read access — without it there is nothing to sync.
    A refresh response may omit ``scope`` or ``refresh_token``; the stored values are then kept.
    """
    granted = data.get("scope") or connection.granted_scope or " ".join(REQUESTED_SCOPES)
    if SCOPE_READ not in scope_set(granted):
        raise VolunHubScopeError(f"VolunHub granted {granted!r}, which does not include {SCOPE_READ}.")

    connection.access_token = data["access_token"]
    if data.get("refresh_token"):
        connection.refresh_token = data["refresh_token"]
    try:
        expires_in = int(data.get("expires_in") or DEFAULT_EXPIRES_IN)
    except (TypeError, ValueError):
        expires_in = DEFAULT_EXPIRES_IN
    connection.access_token_expires_at = timezone.now() + timedelta(seconds=expires_in)
    connection.granted_scope = granted
    connection.status = VolunHubConnection.ACTIVE
    connection.last_error = ""
    return connection


_TOKEN_FIELDS = ("access_token_encrypted", "refresh_token_encrypted", "access_token_expires_at", "granted_scope")


def refresh_access_token(connection):
    """Refresh ``connection``'s access token, persisting the rotated refresh token.

    Serialized on the connection row: after taking the lock, a worker that finds the stored token
    differs from the one it was holding knows another worker already refreshed, and adopts that
    token instead of spending the (now revoked) refresh token a second time.
    """
    held = connection.access_token_encrypted
    failure = None
    with transaction.atomic():
        locked = VolunHubConnection.objects.select_for_update().select_related("client").get(pk=connection.pk)
        if locked.access_token_encrypted != held and locked.access_token_encrypted:
            for field in _TOKEN_FIELDS:
                setattr(connection, field, getattr(locked, field))
            return connection
        if not locked.refresh_token_encrypted:
            failure = "VolunHub issued no refresh token; reconnect to continue syncing."
        else:
            try:
                data = _post_token(
                    locked.client, {"grant_type": "refresh_token", "refresh_token": locked.refresh_token}
                )
                apply_token_response(locked, data)
            except (VolunHubAuthError, VolunHubScopeError) as exc:
                failure = str(exc)
            else:
                locked.save(update_fields=[*_TOKEN_FIELDS, "status", "last_error"])
                for field in (*_TOKEN_FIELDS, "status", "last_error"):
                    setattr(connection, field, getattr(locked, field))
                return connection

    # Outside the atomic block, so the status change is not rolled back with it.
    connection.mark_needs_reauth(failure)
    raise VolunHubAuthError(failure)


def revoke(connection):
    """Best-effort revocation. VolunHub revokes all of this client's tokens for the user."""
    endpoint = connection.client.revocation_endpoint
    token = connection.refresh_token or connection.access_token
    if not endpoint or not token:
        return False
    try:
        response = _send(
            "POST",
            endpoint,
            data={
                "token": token,
                "token_type_hint": "refresh_token" if connection.refresh_token else "access_token",
                "client_id": connection.client.client_id,
            },
        )
    except httpx.HTTPError as exc:
        logger.info("VolunHub revocation failed for %s: %s", connection.user, exc)
        return False
    return response.status_code < 400
