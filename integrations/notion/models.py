"""Persistent state for the two-way Notion sync.

Four models, in the order the flow touches them:

``NotionOAuthFlow``   a pending authorization, binding an unguessable ``state`` to the user who
                      started it — Notion's callback is an unauthenticated browser navigation, so
                      ``state`` is the only thing that says whose tokens these are.
``NotionConnection``  one linked Notion workspace per user, holding the encrypted credentials and
                      the ``bot_id`` that makes echo suppression possible.
``NotionDatabase``    the database this integration created and owns, plus its sync watermarks.
``NotionTaskLink``    one row per mirrored task, carrying the per-side watermarks that decide which
                      way a change flows.
"""

from datetime import timedelta

from django.conf import settings
from django.db import models
from django.utils import timezone

from integrations.crypto import decrypt, encrypt

# How long a started authorization stays usable. Short, because `state` is the whole CSRF defence.
OAUTH_FLOW_TTL = timedelta(minutes=10)


class NotionOAuthFlow(models.Model):
    """An authorization the user has started but not yet completed.

    Single-use and short-lived: :meth:`consume` deletes the row as it resolves it, so a replayed
    callback finds nothing.
    """

    state = models.CharField(max_length=128, unique=True)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="notion_oauth_flows")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "Notion OAuth flow"
        verbose_name_plural = "Notion OAuth flows"

    def __str__(self):
        return f"Notion auth for {self.user} ({self.state[:8]}…)"

    @property
    def is_expired(self):
        return timezone.now() - self.created_at > OAUTH_FLOW_TTL

    @classmethod
    def consume(cls, state):
        """Resolve and delete the flow for ``state``. Returns the user, or None if unusable.

        Unknown, expired and already-consumed states are indistinguishable to the caller on
        purpose — all three mean "do not issue credentials".
        """
        if not state:
            return None
        flow = cls.objects.filter(state=state).select_related("user").first()
        if flow is None:
            return None
        user, expired = flow.user, flow.is_expired
        flow.delete()
        return None if expired else user

    @classmethod
    def purge_expired(cls):
        return cls.objects.filter(created_at__lt=timezone.now() - OAUTH_FLOW_TTL).delete()[0]


class NotionConnection(models.Model):
    """A user's linked Notion workspace."""

    ACTIVE = "active"
    UNPROVISIONED = "unprovisioned"
    NEEDS_REAUTH = "needs_reauth"
    SCHEMA_DRIFT = "schema_drift"
    STATUSES = (
        (ACTIVE, "Active"),
        (UNPROVISIONED, "No database yet"),
        (NEEDS_REAUTH, "Needs re-authorization"),
        (SCHEMA_DRIFT, "Schema changed in Notion"),
    )

    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="notion_connection")

    # Encrypted at rest (integrations/crypto.py). Never logged, never serialized to the SPA.
    access_token_encrypted = models.TextField(blank=True, default="")
    refresh_token_encrypted = models.TextField(blank=True, default="")

    # From the token response. `bot_id` identifies *us* inside the user's workspace, which is how
    # the pull phase recognises its own writes instead of syncing them back (see sync.py).
    bot_id = models.CharField(max_length=64, blank=True, default="")
    workspace_id = models.CharField(max_length=64, blank=True, default="")
    workspace_name = models.CharField(max_length=255, blank=True, default="")
    workspace_icon = models.CharField(max_length=1024, blank=True, default="")

    status = models.CharField(max_length=32, choices=STATUSES, default=UNPROVISIONED)
    last_error = models.TextField(blank=True, default="")

    connected_at = models.DateTimeField(auto_now_add=True)
    last_synced_at = models.DateTimeField(null=True, blank=True)
    last_full_sync_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-connected_at"]
        verbose_name = "Notion connection"
        verbose_name_plural = "Notion connections"

    def __str__(self):
        return f"{self.user} → {self.workspace_name or 'Notion'}"

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

    @property
    def can_refresh(self):
        """Notion does not always issue a refresh token; without one, re-auth is manual."""
        return bool(self.refresh_token_encrypted)

    # -- state ------------------------------------------------------------------------
    def mark_needs_reauth(self, reason=""):
        self.status = self.NEEDS_REAUTH
        self.last_error = reason
        self.save(update_fields=["status", "last_error"])

    def mark_schema_drift(self, reason=""):
        self.status = self.SCHEMA_DRIFT
        self.last_error = reason
        self.save(update_fields=["status", "last_error"])

    @property
    def is_syncable(self):
        """Only an active connection with a finished bootstrap takes part in scheduled syncs."""
        database = getattr(self, "database", None)
        return self.status == self.ACTIVE and database is not None


class NotionDatabase(models.Model):
    """The Notion database this integration created, and the state of syncing against it.

    One per connection, and always created by us: the sync never adopts a pre-existing database.
    All tasks live in a single data source because a Notion page's parent can never be changed —
    with per-project databases, moving a task between projects would mean destroying and recreating
    its page.
    """

    BOOTSTRAP_PENDING = "pending"
    BOOTSTRAP_RUNNING = "running"
    BOOTSTRAP_DONE = "done"
    BOOTSTRAP_STATES = (
        (BOOTSTRAP_PENDING, "Pending"),
        (BOOTSTRAP_RUNNING, "Uploading existing tasks"),
        (BOOTSTRAP_DONE, "Done"),
    )

    connection = models.OneToOneField(NotionConnection, on_delete=models.CASCADE, related_name="database")

    database_id = models.CharField(max_length=64)
    # What every row-level call actually addresses. A database id is rejected where this is required.
    data_source_id = models.CharField(max_length=64)
    parent_page_id = models.CharField(max_length=64)

    # Logical property name -> the Notion property id recorded at provisioning. Properties are
    # addressed by id so that renaming one in Notion does not break the mapping.
    property_ids = models.JSONField(default=dict, blank=True)

    # High-water mark of the incremental pull. Notion rounds `last_edited_time` down to the minute,
    # so the query window deliberately overlaps this (see sync.PULL_OVERLAP).
    pull_watermark = models.DateTimeField(null=True, blank=True)

    bootstrap_state = models.CharField(max_length=16, choices=BOOTSTRAP_STATES, default=BOOTSTRAP_PENDING)
    # Highest TaskItem pk uploaded so far, so an interrupted bootstrap resumes instead of duplicating.
    bootstrap_cursor = models.BigIntegerField(default=0)

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Notion database"
        verbose_name_plural = "Notion databases"

    def __str__(self):
        return f"Notion database {self.database_id} for {self.connection.user}"

    @property
    def url(self):
        """Notion accepts the dashless id in a URL, which is how the SPA links to the database."""
        return f"https://www.notion.so/{self.database_id.replace('-', '')}"

    @property
    def is_bootstrapped(self):
        return self.bootstrap_state == self.BOOTSTRAP_DONE


class NotionTaskLink(models.Model):
    """Ties one ``TaskItem`` to one Notion page, and remembers where each side stood.

    ``task`` is nullable with ``SET_NULL`` so the row doubles as a tombstone: deleting a mirrored
    task locally leaves the link behind holding ``notion_page_id``, which is exactly the signal the
    push phase needs to trash the page upstream. Without it the id would be lost and the page would
    live on in Notion forever.
    """

    database = models.ForeignKey(NotionDatabase, on_delete=models.CASCADE, related_name="links")
    task = models.OneToOneField(
        "tasks.TaskItem", null=True, blank=True, on_delete=models.SET_NULL, related_name="notion_link"
    )
    notion_page_id = models.CharField(max_length=64)

    # The watermark pair. Re-stamped after *every* write on either side, so the engine never reads
    # its own write back as a user edit.
    notion_last_edited_time = models.DateTimeField(null=True, blank=True)
    local_changed_at = models.DateTimeField(null=True, blank=True)
    last_synced_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["database", "notion_page_id"], name="unique_notion_page_per_database"),
        ]
        indexes = [models.Index(fields=["database", "task"])]
        verbose_name = "Notion task link"
        verbose_name_plural = "Notion task links"

    def __str__(self):
        return f"{self.task or '(deleted task)'} ↔ {self.notion_page_id}"

    @property
    def is_tombstone(self):
        """True once the local task is gone and the Notion page still needs trashing."""
        return self.task_id is None

    @property
    def url(self):
        """Link to the mirrored page. Notion accepts the dashless id in a URL."""
        return f"https://www.notion.so/{self.notion_page_id.replace('-', '')}"
