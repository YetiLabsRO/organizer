"""HTTP client for VolunHub's confined task-aggregator API.

Load-bearing beyond request plumbing:

**Path allow-list.** The token can only reach ``/api/v1/projects/tasks…`` and
``/api/v1/projects/projects…``; VolunHub answers 403 everywhere else. The client refuses to even
send a request outside those prefixes, so a bug here can never turn into probing the rest of
VolunHub with a user's credentials.

**Token freshness.** VolunHub states ``expires_in`` (~1h), so the client refreshes *before* a call
when the token is about to expire, and still handles a 401 by refreshing once and retrying.

**All-or-nothing listing.** The sync infers removals from what the listing does *not* contain, so
:meth:`VolunHubAPI.list_assigned_tasks` either returns every page or raises — never a partial list.
"""

import logging
import random
import time
from datetime import timedelta

import httpx
from django.conf import settings
from django.utils import timezone

from integrations.volunhub.exceptions import VolunHubAPIError, VolunHubAuthError, VolunHubError, VolunHubRateLimited
from integrations.volunhub.oauth import refresh_access_token

logger = logging.getLogger(__name__)

TIMEOUT = httpx.Timeout(30.0, connect=10.0)
ALLOWED_PREFIXES = ("/api/v1/projects/tasks", "/api/v1/projects/projects")
TASKS_PATH = "/api/v1/projects/tasks/"
# Refresh this long before the stated expiry rather than racing it.
REFRESH_LEEWAY = timedelta(seconds=60)
# Retries for transient failures (429 / 5xx / network). Auth failures and other 4xx are not retried.
MAX_RETRIES = 4
# VolunHub pages at 50; this caps a runaway loop at 10 000 tasks.
MAX_PAGES = 200


class VolunHubAPI:
    """Bound to one :class:`~integrations.volunhub.models.VolunHubConnection`."""

    def __init__(self, connection, client=None):
        self.connection = connection
        self._client = client or httpx.Client(timeout=TIMEOUT)
        self._owns_client = client is None

    def __enter__(self):
        return self

    def __exit__(self, *exc_info):
        self.close()
        return False

    def close(self):
        if self._owns_client:
            self._client.close()

    # -- plumbing ---------------------------------------------------------------------
    def _ensure_fresh_token(self):
        expires_at = self.connection.access_token_expires_at
        if expires_at is not None and expires_at - timezone.now() < REFRESH_LEEWAY:
            refresh_access_token(self.connection)

    def request(self, method, path, *, json=None, params=None, _refreshed=False):
        """Issue one API call: allow-list, refresh, backoff. Returns ``(status_code, body)``."""
        if not path.startswith(ALLOWED_PREFIXES):
            raise VolunHubError(f"Refusing to call {path}: outside the confined VolunHub task API.")
        if not _refreshed:
            self._ensure_fresh_token()
        url = f"{settings.VOLUNHUB_BASE_URL}{path}"

        for attempt in range(MAX_RETRIES):
            try:
                response = self._client.request(
                    method,
                    url,
                    json=json,
                    params=params,
                    headers={"Authorization": f"Bearer {self.connection.access_token}", "Accept": "application/json"},
                )
            except httpx.HTTPError as exc:
                if attempt == MAX_RETRIES - 1:
                    raise VolunHubAPIError(f"Could not reach VolunHub: {exc}") from exc
                self._sleep_backoff(attempt)
                continue

            if response.status_code == 401:
                if _refreshed:
                    self.connection.mark_needs_reauth("VolunHub rejected the access token after a refresh.")
                    raise VolunHubAuthError("VolunHub rejected the refreshed access token.")
                refresh_access_token(self.connection)
                return self.request(method, path, json=json, params=params, _refreshed=True)

            if response.status_code == 429:
                retry_after = _float_header(response, "Retry-After", default=2.0)
                if attempt == MAX_RETRIES - 1:
                    raise VolunHubRateLimited("VolunHub rate limit exceeded.", retry_after=retry_after)
                time.sleep(min(retry_after, 60.0))
                continue

            if response.status_code >= 500:
                if attempt == MAX_RETRIES - 1:
                    raise VolunHubAPIError(f"VolunHub is unavailable ({response.status_code}).", response.status_code)
                self._sleep_backoff(attempt)
                continue

            return response.status_code, _json_or_empty(response)

        raise VolunHubAPIError("Exhausted retries talking to VolunHub.")

    def _call(self, method, path, *, json=None, params=None, allow_404=False):
        """``request`` that raises VolunHubAPIError on any 4xx (or returns None on 404 if allowed)."""
        status_code, body = self.request(method, path, json=json, params=params)
        if status_code == 404 and allow_404:
            return None
        if status_code >= 400:
            detail = body.get("detail") if isinstance(body, dict) else None
            raise VolunHubAPIError(detail or f"VolunHub returned {status_code}", status_code=status_code, body=body)
        return body

    @staticmethod
    def _sleep_backoff(attempt):
        """Exponential backoff with jitter, so parallel workers do not retry in lockstep."""
        time.sleep(min(2**attempt, 16) * (0.5 + random.random()))  # noqa: S311 - jitter, not crypto

    # -- tasks ------------------------------------------------------------------------
    def list_assigned_tasks(self):
        """Every task personally assigned to the user, across all pages, ordered by id.

        ``ordering=id`` because VolunHub's default (``-start_date``) is nullable and has no
        tiebreaker, so rows could drift between pages. Raises on any failed page.
        """
        tasks = []
        for page in range(1, MAX_PAGES + 1):
            data = self._call("GET", TASKS_PATH, params={"mine": "true", "ordering": "id", "page": page})
            tasks.extend(data.get("results") or [])
            if not data.get("next"):
                return tasks
        raise VolunHubAPIError(f"VolunHub task listing exceeded {MAX_PAGES} pages.")

    def get_task(self, task_id):
        """The task by id, or None when VolunHub answers 404 (deleted, or no longer visible)."""
        return self._call("GET", f"{TASKS_PATH}{int(task_id)}/", allow_404=True)

    def patch_task(self, task_id, fields):
        """Partial update; VolunHub answers with the full task."""
        return self._call("PATCH", f"{TASKS_PATH}{int(task_id)}/", json=fields)

    def set_state(self, task_id, state):
        """Move the task through VolunHub's workflow. Same-state requests are idempotent successes."""
        return self._call("POST", f"{TASKS_PATH}{int(task_id)}/status/", json={"state": state})


def _json_or_empty(response):
    try:
        data = response.json()
    except ValueError:
        return {}
    return data if isinstance(data, dict) else {}


def _float_header(response, name, default=0.0):
    try:
        return float(response.headers.get(name, default))
    except (TypeError, ValueError):
        return default
