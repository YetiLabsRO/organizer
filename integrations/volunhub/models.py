"""Persistent state for the two-way VolunHub sync.

Five models, in the order the flow touches them:

``VolunHubOAuthClient``  the instance-wide public client registered once with VolunHub (RFC 7591).
                         The OAuth client is the Organizer *deployment*, not a user.
``VolunHubOAuthFlow``    a pending authorization, binding an unguessable ``state`` and the PKCE
                         ``code_verifier`` to the user who started it.
``VolunHubConnection``   one linked VolunHub account per user, holding the encrypted credentials.
``VolunHubProjectLink``  VolunHub project id -> local ``Project``. Global, because ``Project`` is.
``VolunHubTaskLink``     one row per imported task, carrying the snapshot the three-way merge
                         compares both sides against.

Task links hang off the *user*, not the connection, so they outlive a disconnect: reconnecting
re-attaches the same local tasks instead of importing duplicates. VolunHub task ids are global, so
matching by id is safe even if the user reconnects a different account.
"""

from datetime import timedelta

from django.conf import settings
from django.db import models
from django.utils import timezone

from integrations.crypto import decrypt, encrypt

# How long a started authorization stays usable. Short, because `state` is the whole CSRF defence.
OAUTH_FLOW_TTL = timedelta(minutes=10)

SCOPE_READ = "mcp:tasks:read"
SCOPE_WRITE = "mcp:tasks:write"
# Exactly this set is what pins a VolunHub client to the confined tasks/projects surface. Anything
# broader (or no scope at all) yields a full-scope client, which we refuse to hold.
REQUESTED_SCOPES = (SCOPE_READ, SCOPE_WRITE)


def scope_set(value):
    """A space-separated OAuth scope string as a set."""
    return set((value or "").split())


class VolunHubOAuthClient(models.Model):
    """The public client this deployment registered with VolunHub, plus the endpoints it uses.

    Unique per (base URL, redirect URI): changing ``VOLUNHUB_REDIRECT_URI`` makes the next connect
    register a fresh client, because VolunHub matches redirect URIs byte for byte. Existing
    connections keep refreshing through the client that issued their tokens.
    """

    base_url = models.URLField(max_length=512)
    redirect_uri = models.URLField(max_length=1024)
    client_id = models.CharField(max_length=255)
    scope = models.CharField(max_length=255, blank=True, default="")
    # Discovered from /.well-known/oauth-authorization-server (with documented fallbacks).
    authorization_endpoint = models.URLField(max_length=1024)
    token_endpoint = models.URLField(max_length=1024)
    revocation_endpoint = models.URLField(max_length=1024, blank=True, default="")
    registered_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["base_url", "redirect_uri"], name="unique_volunhub_client_per_redirect"),
        ]
        verbose_name = "VolunHub OAuth client"
        verbose_name_plural = "VolunHub OAuth clients"

    def __str__(self):
        return f"{self.client_id} @ {self.base_url}"


class VolunHubOAuthFlow(models.Model):
    """An authorization the user has started but not yet completed. Single-use and short-lived."""

    state = models.CharField(max_length=128, unique=True)
    code_verifier = models.CharField(max_length=128)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="volunhub_oauth_flows")
    client = models.ForeignKey(VolunHubOAuthClient, on_delete=models.CASCADE, related_name="flows")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "VolunHub OAuth flow"
        verbose_name_plural = "VolunHub OAuth flows"

    def __str__(self):
        return f"VolunHub auth for {self.user} ({self.state[:8]}…)"

    @property
    def is_expired(self):
        return timezone.now() - self.created_at > OAUTH_FLOW_TTL

    @classmethod
    def consume(cls, state):
        """Resolve and delete the flow for ``state``. Returns the flow, or None if unusable.

        Unknown, expired and already-consumed states are indistinguishable to the caller on
        purpose — all three mean "do not issue credentials".
        """
        if not state:
            return None
        flow = cls.objects.filter(state=state).select_related("user", "client").first()
        if flow is None:
            return None
        expired = flow.is_expired
        flow.delete()
        return None if expired else flow

    @classmethod
    def purge_expired(cls):
        return cls.objects.filter(created_at__lt=timezone.now() - OAUTH_FLOW_TTL).delete()[0]


class VolunHubConnection(models.Model):
    """A user's linked VolunHub account."""

    ACTIVE = "active"
    NEEDS_REAUTH = "needs_reauth"
    STATUSES = (
        (ACTIVE, "Active"),
        (NEEDS_REAUTH, "Needs re-authorization"),
    )

    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="volunhub_connection")
    # Tokens are bound to the client that issued them, so refreshes must keep using it.
    client = models.ForeignKey(VolunHubOAuthClient, on_delete=models.PROTECT, related_name="connections")

    # Encrypted at rest (integrations/crypto.py). Never logged, never serialized to the SPA.
    access_token_encrypted = models.TextField(blank=True, default="")
    refresh_token_encrypted = models.TextField(blank=True, default="")
    access_token_expires_at = models.DateTimeField(null=True, blank=True)
    granted_scope = models.CharField(max_length=255, blank=True, default="")

    status = models.CharField(max_length=32, choices=STATUSES, default=ACTIVE)
    # Switched off when VolunHub refuses a content PATCH (its docs promise status-only writes); status
    # keeps flowing. Reset by reconnecting or by an explicit retry from the UI.
    content_push_enabled = models.BooleanField(default=True)
    last_error = models.TextField(blank=True, default="")

    connected_at = models.DateTimeField(auto_now_add=True)
    last_synced_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-connected_at"]
        verbose_name = "VolunHub connection"
        verbose_name_plural = "VolunHub connections"

    def __str__(self):
        return f"{self.user} → VolunHub"

    # -- credentials ------------------------------------------------------------------
    @property
    def access_token(self):
        return decrypt(self.access_token_encrypted)

    @access_token.setter
    def access_token(self, value):
        self.access_token_encrypted = encrypt(value)

    @property
    def refresh_token(self):
        return decrypt(self.refresh_token_encrypted)

    @refresh_token.setter
    def refresh_token(self, value):
        self.refresh_token_encrypted = encrypt(value)

    # -- capabilities -----------------------------------------------------------------
    @property
    def can_write(self):
        """The user may untick the write permission on VolunHub's consent screen."""
        return SCOPE_WRITE in scope_set(self.granted_scope)

    @property
    def pushes_content(self):
        return self.can_write and self.content_push_enabled

    # -- state ------------------------------------------------------------------------
    def mark_needs_reauth(self, reason=""):
        self.status = self.NEEDS_REAUTH
        self.last_error = reason
        self.save(update_fields=["status", "last_error"])

    def disable_content_push(self, reason=""):
        self.content_push_enabled = False
        self.last_error = reason
        self.save(update_fields=["content_push_enabled", "last_error"])


class VolunHubProjectLink(models.Model):
    """A VolunHub project and the local ``Project`` its tasks land in.

    Global rather than per user: ``Project`` has no owner, so two users on the same VolunHub project
    share one local project. ``auto_created`` is true while the project is the one the sync created;
    merging into an existing project clears it, and from then on the sync never renames the project.
    """

    external_id = models.BigIntegerField(unique=True)
    external_slug = models.CharField(max_length=255, blank=True, default="")
    external_name = models.CharField(max_length=1024, blank=True, default="")
    # SET_NULL: deleting the local project leaves the link behind, so the sync does not quietly
    # re-create a project the user removed — its tasks import project-less until merged again.
    project = models.ForeignKey(
        "tasks.Project", null=True, blank=True, on_delete=models.SET_NULL, related_name="volunhub_links"
    )
    auto_created = models.BooleanField(default=False)

    class Meta:
        ordering = ["external_name"]
        verbose_name = "VolunHub project link"
        verbose_name_plural = "VolunHub project links"

    def __str__(self):
        return f"{self.external_name or self.external_id} → {self.project or '(no project)'}"


class VolunHubTaskLink(models.Model):
    """Ties one ``TaskItem`` to one VolunHub task, and remembers what both sides last agreed on.

    ``task`` is nullable with ``SET_NULL`` so a local delete leaves a tombstone: the task is then
    neither re-imported nor deleted upstream (Organizer never deletes in VolunHub).
    """

    ACTIVE = "active"
    REMOVED = "removed"
    STATES = ((ACTIVE, "Synced"), (REMOVED, "Removed from VolunHub"))

    UNASSIGNED = "unassigned"
    DELETED = "deleted"
    DISCONNECTED = "disconnected"
    REMOVED_REASONS = (
        (UNASSIGNED, "Unassigned in VolunHub"),
        (DELETED, "Deleted in VolunHub"),
        (DISCONNECTED, "VolunHub disconnected"),
    )

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="volunhub_task_links")
    external_id = models.BigIntegerField()
    task = models.OneToOneField(
        "tasks.TaskItem", null=True, blank=True, on_delete=models.SET_NULL, related_name="volunhub_link"
    )

    state = models.CharField(max_length=16, choices=STATES, default=ACTIVE)
    removed_reason = models.CharField(max_length=16, choices=REMOVED_REASONS, blank=True, default="")
    removed_at = models.DateTimeField(null=True, blank=True)

    # The last values both sides agreed on, in Organizer representation (see mapping.py). The merge
    # compares each side against this, so a value we wrote ourselves never reads back as a change.
    snapshot = models.JSONField(default=dict, blank=True)
    external_project_id = models.BigIntegerField(null=True, blank=True)

    last_error = models.TextField(blank=True, default="")
    last_synced_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["user", "external_id"], name="unique_volunhub_task_per_user"),
        ]
        indexes = [models.Index(fields=["user", "state"])]
        verbose_name = "VolunHub task link"
        verbose_name_plural = "VolunHub task links"

    def __str__(self):
        return f"{self.task or '(deleted task)'} ↔ VolunHub #{self.external_id}"

    @property
    def is_tombstone(self):
        return self.task_id is None

    @property
    def url(self):
        """The task's page in VolunHub's web UI (``projects:task_detail``)."""
        return f"{settings.VOLUNHUB_BASE_URL}/proiecte/task-uri/{self.external_id}/"

    def mark_removed(self, reason):
        self.state = self.REMOVED
        self.removed_reason = reason
        self.removed_at = timezone.now()
        self.save(update_fields=["state", "removed_reason", "removed_at"])

    def reattach(self):
        self.state = self.ACTIVE
        self.removed_reason = ""
        self.removed_at = None
