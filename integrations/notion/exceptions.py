"""Error types raised by the Notion integration.

The distinction that matters to callers is *recoverable by retrying* (``NotionRateLimited``, a
transient ``NotionAPIError``) versus *recoverable only by the user* (``NotionAuthError`` →
re-authorize, ``NotionSchemaDriftError`` → repair the database). The sync engine turns the latter
two into a connection status rather than an exception that kills the scheduled run.
"""


class NotionError(Exception):
    """Base class for every failure originating from the Notion integration."""


class NotionNotConfigured(NotionError):
    """NOTION_CLIENT_ID / NOTION_CLIENT_SECRET are not set, so the integration is disabled."""


class NotionAuthError(NotionError):
    """The stored credentials cannot be used or refreshed; the user must reconnect."""


class NotionAPIError(NotionError):
    """A Notion API call failed. Carries the HTTP status and Notion's own error code."""

    def __init__(self, message, status_code=None, code=""):
        super().__init__(message)
        self.status_code = status_code
        self.code = code


class NotionRateLimited(NotionAPIError):
    """Notion returned 429. ``retry_after`` is the delay in seconds it asked for."""

    def __init__(self, message, retry_after=0.0, status_code=429, code="rate_limited"):
        super().__init__(message, status_code=status_code, code=code)
        self.retry_after = retry_after


class NotionSchemaDriftError(NotionError):
    """A property the sync depends on no longer exists in the Notion data source."""
