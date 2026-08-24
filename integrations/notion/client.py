"""HTTP client for the Notion API, pinned to the data-source era of the API.

Two things here are load-bearing beyond plain request plumbing:

**Pacing.** Notion's limit is documented as an *average* of ~3 requests/second rather than a hard
burst ceiling, so the client paces proactively (a minimum gap between requests) instead of only
reacting to 429s. Bootstrap uploads one page per task, so without pacing a few hundred tasks would
walk straight into rate limiting.

**Versioning.** Every call sends ``Notion-Version``. Pinned to 2025-09-03 or later, rows live in a
*data source* inside a database, and ``/v1/data_sources/{id}/query`` is the only way to read them —
passing a database id where a data source id is expected is rejected outright.
"""

import logging
import random
import time

import httpx
from django.conf import settings

from integrations.notion.exceptions import NotionAPIError, NotionAuthError, NotionRateLimited
from integrations.notion.oauth import refresh_access_token

logger = logging.getLogger(__name__)

API_ROOT = "https://api.notion.com/v1"
TIMEOUT = httpx.Timeout(60.0, connect=15.0)

# Notion allows ~3 requests/second on average. Leave a little headroom.
MIN_REQUEST_INTERVAL = 1.0 / 3.0
# Retries for transient failures (429 / 5xx). Auth failures and 4xx are not retried.
MAX_RETRIES = 5
# Notion's page size ceiling for query results.
MAX_PAGE_SIZE = 100


class NotionClient:
    """Bound to one :class:`~integrations.notion.models.NotionConnection`.

    Refreshes the access token transparently on a 401 and retries the call once. Because Notion's
    token response carries no ``expires_in``, that reactive path is the *only* way expiry is ever
    discovered.
    """

    def __init__(self, connection, client=None):
        self.connection = connection
        self._client = client or httpx.Client(timeout=TIMEOUT)
        self._owns_client = client is None
        self._last_request_at = 0.0

    def __enter__(self):
        return self

    def __exit__(self, *exc_info):
        self.close()
        return False

    def close(self):
        if self._owns_client:
            self._client.close()

    # -- plumbing ---------------------------------------------------------------------
    def _headers(self):
        return {
            "Authorization": f"Bearer {self.connection.access_token}",
            "Notion-Version": settings.NOTION_API_VERSION,
            "Content-Type": "application/json",
        }

    def _pace(self):
        """Sleep just long enough to keep the average request rate under Notion's limit."""
        elapsed = time.monotonic() - self._last_request_at
        if elapsed < MIN_REQUEST_INTERVAL:
            time.sleep(MIN_REQUEST_INTERVAL - elapsed)
        self._last_request_at = time.monotonic()

    def request(self, method, path, *, json=None, params=None, _refreshed=False):
        """Issue one API call, handling pacing, refresh-on-401 and backoff on 429/5xx."""
        url = f"{API_ROOT}{path}"

        for attempt in range(MAX_RETRIES):
            self._pace()
            try:
                response = self._client.request(method, url, json=json, params=params, headers=self._headers())
            except httpx.HTTPError as exc:
                if attempt == MAX_RETRIES - 1:
                    raise NotionAPIError(f"Could not reach Notion: {exc}") from exc
                self._sleep_backoff(attempt)
                continue

            if response.status_code == 401:
                # Expiry is only ever discovered here. Refresh once, then retry the original call.
                if _refreshed:
                    self.connection.mark_needs_reauth("Notion rejected the access token after a refresh.")
                    raise NotionAuthError("Notion rejected the refreshed access token.")
                refresh_access_token(self.connection)
                return self.request(method, path, json=json, params=params, _refreshed=True)

            if response.status_code == 429:
                retry_after = _float_header(response, "Retry-After", default=1.0)
                if attempt == MAX_RETRIES - 1:
                    raise NotionRateLimited("Notion rate limit exceeded.", retry_after=retry_after)
                logger.info("Notion rate limited; waiting %.1fs", retry_after)
                time.sleep(retry_after)
                continue

            if response.status_code >= 500 or response.status_code == 529:
                if attempt == MAX_RETRIES - 1:
                    raise NotionAPIError(f"Notion is unavailable ({response.status_code}).", response.status_code)
                self._sleep_backoff(attempt)
                continue

            if response.status_code >= 400:
                body = _json_or_empty(response)
                raise NotionAPIError(
                    body.get("message") or f"Notion returned {response.status_code}",
                    status_code=response.status_code,
                    code=body.get("code", ""),
                )

            return _json_or_empty(response)

        raise NotionAPIError("Exhausted retries talking to Notion.")

    @staticmethod
    def _sleep_backoff(attempt):
        """Exponential backoff with jitter, so parallel workers do not retry in lockstep."""
        time.sleep(min(2**attempt, 16) * (0.5 + random.random()))  # noqa: S311 - jitter, not crypto

    def _paginate(self, method, path, *, json=None):
        """Yield every result across Notion's cursor pagination."""
        payload = dict(json or {})
        payload.setdefault("page_size", MAX_PAGE_SIZE)
        while True:
            data = self.request(method, path, json=payload)
            yield from data.get("results", [])
            if not data.get("has_more"):
                return
            payload["start_cursor"] = data["next_cursor"]

    # -- pages the integration can see -------------------------------------------------
    def search_pages(self, query=""):
        """Pages the user shared with this integration during consent.

        This is the candidate list for the database's parent — the integration genuinely cannot
        reach anything the user did not tick on Notion's consent screen.
        """
        payload = {"filter": {"property": "object", "value": "page"}}
        if query:
            payload["query"] = query
        return list(self._paginate("POST", "/search", json=payload))

    # -- database / data source --------------------------------------------------------
    def create_database(self, parent_page_id, title, properties, icon=None):
        """Create the task database under ``parent_page_id``.

        In 2025-09-03 the schema moved under ``initial_data_source``, separating what belongs to the
        database (title, icon, parent) from what belongs to its data source (the properties).
        """
        payload = {
            "parent": {"type": "page_id", "page_id": parent_page_id},
            "title": [{"type": "text", "text": {"content": title}}],
            "initial_data_source": {"properties": properties},
        }
        if icon:
            payload["icon"] = icon
        return self.request("POST", "/databases", json=payload)

    def retrieve_database(self, database_id):
        """Retrieve a database — notably its ``data_sources`` array, which holds the id we need."""
        return self.request("GET", f"/databases/{database_id}")

    def retrieve_data_source(self, data_source_id):
        return self.request("GET", f"/data_sources/{data_source_id}")

    def update_data_source(self, data_source_id, properties):
        """Patch the schema — used to seed select/multi-select options before bootstrap."""
        return self.request("PATCH", f"/data_sources/{data_source_id}", json={"properties": properties})

    def query_data_source(self, data_source_id, *, filter=None, sorts=None):  # noqa: A002 - Notion's field name
        """Every row matching ``filter``, following pagination.

        Returns non-archived rows only; Notion offers no way to ask for trashed pages here, which is
        why deletions made in Notion can only be noticed by a full reconciliation sweep.
        """
        payload = {}
        if filter:
            payload["filter"] = filter
        if sorts:
            payload["sorts"] = sorts
        return list(self._paginate("POST", f"/data_sources/{data_source_id}/query", json=payload))

    # -- pages -------------------------------------------------------------------------
    def create_page(self, data_source_id, properties):
        payload = {
            "parent": {"type": "data_source_id", "data_source_id": data_source_id},
            "properties": properties,
        }
        return self.request("POST", "/pages", json=payload)

    def retrieve_page(self, page_id):
        """Works on trashed pages too — which is how the full sweep confirms a deletion."""
        return self.request("GET", f"/pages/{page_id}")

    def update_page(self, page_id, properties):
        # A page's parent can never be changed, so this only ever carries properties. Moving a task
        # between projects is a property update precisely because re-parenting is impossible.
        return self.request("PATCH", f"/pages/{page_id}", json={"properties": properties})

    def trash_page(self, page_id):
        """Move a page to Notion's trash (recoverable there for 30 days by default)."""
        return self.request("PATCH", f"/pages/{page_id}", json={"in_trash": True})


def _json_or_empty(response):
    try:
        return response.json()
    except ValueError:
        return {}


def _float_header(response, name, default=0.0):
    try:
        return float(response.headers.get(name, default))
    except (TypeError, ValueError):
        return default
