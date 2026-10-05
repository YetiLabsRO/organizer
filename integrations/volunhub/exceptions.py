"""Error types raised by the VolunHub integration.

As with Notion, what matters to callers is *recoverable by retrying* (``VolunHubRateLimited``, a
transient ``VolunHubAPIError``) versus *recoverable only by the user* (``VolunHubAuthError`` →
reconnect). The sync engine turns the latter into a connection status rather than an exception that
kills the scheduled run.
"""


class VolunHubError(Exception):
    """Base class for every failure originating from the VolunHub integration."""


class VolunHubNotConfigured(VolunHubError):
    """VOLUNHUB_BASE_URL / VOLUNHUB_REDIRECT_URI are unusable, so the integration is disabled."""


class VolunHubAuthError(VolunHubError):
    """The stored credentials cannot be used or refreshed; the user must reconnect."""


class VolunHubScopeError(VolunHubError):
    """VolunHub granted (or registered) a scope set we refuse to work with."""


class VolunHubAPIError(VolunHubError):
    """A VolunHub API call failed. Carries the HTTP status and the decoded body, if any."""

    def __init__(self, message, status_code=None, body=None):
        super().__init__(message)
        self.status_code = status_code
        self.body = body or {}


class VolunHubRateLimited(VolunHubAPIError):
    """VolunHub returned 429. ``retry_after`` is the delay in seconds it asked for."""

    def __init__(self, message, retry_after=0.0):
        super().__init__(message, status_code=429)
        self.retry_after = retry_after
