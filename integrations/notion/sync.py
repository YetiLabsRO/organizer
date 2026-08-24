"""The two-way sync engine.

One run, per connection, is: **bootstrap** (once) → **pull** → **push**, in that order. Pull runs
before push so pages that arrived from Notion have local ids and links before push goes looking for
unlinked local tasks — otherwise the same task would be created on both sides.

Three invariants carry the design:

**1. Echo suppression.** Every Notion page reports who edited it last, and the OAuth exchange told
us our own ``bot_id``. A page whose last editor is us is our own write, and is skipped. This is the
primary defence against sync ping-pong, and it matters more here than it would elsewhere because
Notion's timestamps are too coarse to lean on (below).

**2. Watermarks are re-stamped after every write, on both sides.** ``TaskItem.changed_date`` is
``auto_now``, so the sync's own inbound write bumps it; without re-stamping, the next run would read
that as a user edit and push it straight back, forever. Every write path here ends in
:func:`_stamp`.

**3. Notion's ``last_edited_time`` is rounded down to the minute.** So the incremental query window
deliberately overlaps (:data:`PULL_OVERLAP`), applies must be idempotent, and two edits inside the
same minute cannot be ordered at all — which is why a same-minute conflict resolves in Organizer's
favour rather than pretending the timestamps settle it.
"""

import logging
from datetime import UTC, timedelta

from django.conf import settings
from django.db import transaction
from django.utils import timezone
from django.utils.dateparse import parse_datetime

from integrations.notion import mapping, schema
from integrations.notion.client import NotionClient
from integrations.notion.exceptions import NotionAuthError, NotionSchemaDriftError
from integrations.notion.models import NotionTaskLink
from tasks.models import TaskItem

logger = logging.getLogger(__name__)

# How far back the incremental query reaches beyond the watermark. Notion rounds `last_edited_time`
# down to the minute, so a 2-minute overlap covers both the rounding and clock skew.
PULL_OVERLAP = timedelta(minutes=2)
# Tasks uploaded per bootstrap batch before the cursor is persisted.
BOOTSTRAP_BATCH = 50


class SyncReport:
    """What one run did — returned to the caller and logged; nothing depends on its shape."""

    def __init__(self):
        self.pulled = 0
        self.created_locally = 0
        self.updated_locally = 0
        self.pushed = 0
        self.created_remotely = 0
        self.trashed = 0
        self.deleted_locally = 0
        self.skipped_echo = 0
        self.conflicts = 0

    def as_dict(self):
        return self.__dict__.copy()

    def __str__(self):
        return ", ".join(f"{key}={value}" for key, value in self.__dict__.items() if value)


def sync_connection(connection, *, full=False, client=None):
    """Synchronize one connection. Returns a :class:`SyncReport`.

    Auth and schema problems become a connection *status* rather than an exception, so one broken
    connection never aborts a scheduled batch.
    """
    report = SyncReport()
    database = getattr(connection, "database", None)
    if database is None:
        logger.info("Notion connection for %s has no database yet; nothing to sync.", connection.user)
        return report

    owns_client = client is None
    client = client or NotionClient(connection)
    try:
        data_source = client.retrieve_data_source(database.data_source_id)
        schema.check_drift(data_source, database.property_ids)
        names = schema.resolve_property_names(data_source, database.property_ids)

        if not database.is_bootstrapped:
            bootstrap(connection, database, client, names, report)
            return report

        full = full or _is_full_sync_due(connection)
        _pull(connection, database, client, names, report, full=full)
        _push(connection, database, client, names, report)

        now = timezone.now()
        connection.last_synced_at = now
        fields = ["last_synced_at"]
        if full:
            connection.last_full_sync_at = now
            fields.append("last_full_sync_at")
        if connection.status != connection.ACTIVE:
            connection.status = connection.ACTIVE
            connection.last_error = ""
            fields += ["status", "last_error"]
        connection.save(update_fields=fields)

        logger.info("Notion sync for %s: %s", connection.user, report or "no changes")
    except NotionSchemaDriftError as exc:
        connection.mark_schema_drift(str(exc))
        logger.warning("Notion schema drift for %s: %s", connection.user, exc)
    except NotionAuthError as exc:
        # refresh_access_token/mark_needs_reauth already recorded the status.
        logger.warning("Notion auth failed for %s: %s", connection.user, exc)
    finally:
        if owns_client:
            client.close()
    return report


def _is_full_sync_due(connection):
    if connection.last_full_sync_at is None:
        return True
    return timezone.now() - connection.last_full_sync_at >= timedelta(hours=settings.NOTION_FULL_SYNC_HOURS)


# --------------------------------------------------------------------------------------
# Bootstrap
# --------------------------------------------------------------------------------------
def bootstrap(connection, database, client, names, report=None):
    """Upload every task the user owns into the freshly created, empty database.

    Resumable: ``bootstrap_cursor`` holds the highest task pk uploaded, so a worker that dies
    mid-run continues instead of creating a second page for everything it already did.
    """
    report = report or SyncReport()
    created_links = []
    if database.bootstrap_state != database.BOOTSTRAP_RUNNING:
        database.bootstrap_state = database.BOOTSTRAP_RUNNING
        database.save(update_fields=["bootstrap_state"])

    while True:
        batch = list(
            TaskItem.objects.filter(owner=connection.user, pk__gt=database.bootstrap_cursor)
            .order_by("pk")
            .prefetch_related("tags")[:BOOTSTRAP_BATCH]
        )
        if not batch:
            break
        for task in batch:
            # Relations are resolved in a second pass, once every parent has a page.
            if not NotionTaskLink.objects.filter(database=database, task=task).exists():
                link = _create_page(database, client, names, task, report)
                if link is not None:
                    created_links.append(link)
            database.bootstrap_cursor = task.pk
        database.save(update_fields=["bootstrap_cursor"])

    _link_parents(database, client, names, created_links)

    database.bootstrap_state = database.BOOTSTRAP_DONE
    database.pull_watermark = timezone.now()
    database.save(update_fields=["bootstrap_state", "pull_watermark"])

    connection.status = connection.ACTIVE
    connection.last_synced_at = timezone.now()
    connection.save(update_fields=["status", "last_synced_at"])
    logger.info("Notion bootstrap finished for %s: %s pages", connection.user, report.created_remotely)
    return report


# --------------------------------------------------------------------------------------
# Pull: Notion -> Organizer
# --------------------------------------------------------------------------------------
def _pull(connection, database, client, names, report, full=False):
    """Apply Notion-side changes locally.

    A *full* pull walks the whole data source with no filter — the only pass that can notice a page
    trashed in Notion, since the query endpoint returns non-archived rows only and cannot be asked
    about trashed ones.
    """
    query_filter = None
    if not full and database.pull_watermark:
        since = database.pull_watermark - PULL_OVERLAP
        query_filter = {
            "timestamp": "last_edited_time",
            "last_edited_time": {"on_or_after": since.isoformat()},
        }

    started_at = timezone.now()
    pages = client.query_data_source(
        database.data_source_id,
        filter=query_filter,
        sorts=[{"timestamp": "last_edited_time", "direction": "ascending"}],
    )

    seen_page_ids = set()
    for page in pages:
        seen_page_ids.add(page["id"])
        report.pulled += 1
        _apply_page(connection, database, client, names, page, report)

    if full:
        _reap_missing_pages(database, client, seen_page_ids, report)

    database.pull_watermark = started_at
    database.save(update_fields=["pull_watermark"])


def _is_own_edit(connection, page):
    """True when the page's last editor is this integration — i.e. our own write echoing back."""
    editor_id = (page.get("last_edited_by") or {}).get("id")
    return bool(connection.bot_id) and editor_id == connection.bot_id


@transaction.atomic
def _apply_page(connection, database, client, names, page, report):
    link = NotionTaskLink.objects.filter(database=database, notion_page_id=page["id"]).select_related("task").first()
    page_edited = _parse_notion_time(page.get("last_edited_time"))

    if link is None:
        if _is_own_edit(connection, page):
            # A page we just created, coming back inside the overlap window. The push phase already
            # linked it; if it did not, this is a page we made and lost track of — skip it rather
            # than importing a duplicate of a task we already have.
            report.skipped_echo += 1
            return
        _create_task_from_page(connection, database, names, page, page_edited, report)
        return

    if link.task is None:
        # Locally deleted; the push phase owns this row and will trash the page.
        return

    if _is_own_edit(connection, page):
        report.skipped_echo += 1
        # Advance the *remote* watermark only. Stamping the local side here would consume a local
        # edit the push phase has not sent yet, silently dropping the user's change.
        _stamp(link, page_edited=page_edited, task=None)
        return

    remote_changed = link.notion_last_edited_time is None or (
        page_edited is not None and page_edited > link.notion_last_edited_time
    )
    local_changed = link.local_changed_at is None or link.task.changed_date > link.local_changed_at

    if not remote_changed:
        return

    if local_changed and _organizer_wins(link.task.changed_date, page_edited):
        # Both sides moved and Organizer is the more recent (or the tie-break winner). Leave the
        # task alone; the push phase will overwrite the page.
        report.conflicts += 1
        logger.info("Notion conflict on task %s resolved in Organizer's favour", link.task_id)
        return
    if local_changed:
        report.conflicts += 1
        logger.info("Notion conflict on task %s resolved in Notion's favour", link.task_id)

    task = link.task
    changed, completed_date = mapping.apply_page_to_task(page, task, names)
    tags_changed = mapping.sync_tags(task, mapping.read_multi_select(page, names, schema.TAGS))
    parent_changed = _apply_parent(database, names, page, task)

    if changed or parent_changed:
        task.save()
    mapping.apply_completed_date(task, completed_date)
    if changed or tags_changed or parent_changed:
        report.updated_locally += 1

    task.refresh_from_db()
    _stamp(link, page_edited=page_edited, task=task)


def _organizer_wins(local_changed_at, page_edited):
    """Decide a both-sides-changed conflict.

    Most recent wins — except that Notion's timestamp is rounded down to the minute, so when the two
    land in the same minute they carry no ordering information at all. That tie goes to Organizer:
    it is the source of truth and the finer-grained clock.
    """
    if page_edited is None:
        return True
    if local_changed_at.replace(second=0, microsecond=0) == page_edited.replace(second=0, microsecond=0):
        return True
    return local_changed_at > page_edited


def _create_task_from_page(connection, database, names, page, page_edited, report):
    task = TaskItem(owner=connection.user)
    _, completed_date = mapping.apply_page_to_task(page, task, names)
    if not task.title:
        task.title = "Untitled"
    task.save()
    mapping.sync_tags(task, mapping.read_multi_select(page, names, schema.TAGS))
    mapping.apply_completed_date(task, completed_date)
    _apply_parent(database, names, page, task, save=True)

    task.refresh_from_db()
    link = NotionTaskLink.objects.create(database=database, task=task, notion_page_id=page["id"])
    _stamp(link, page_edited=page_edited, task=task)
    report.created_locally += 1
    logger.info("Created task %s from Notion page %s", task.pk, page["id"])


def _apply_parent(database, names, page, task, save=False):
    """Resolve the parent-task relation to a local task, if the parent is mirrored."""
    related = mapping.read_relation_ids(page, names, schema.PARENT_TASK)
    parent_task = None
    if related:
        parent_link = (
            NotionTaskLink.objects.filter(database=database, notion_page_id=related[0])
            .exclude(task=None)
            .select_related("task")
            .first()
        )
        parent_task = parent_link.task if parent_link else None
    # Never let a task become its own parent through a relation pointing at itself.
    if parent_task is not None and parent_task.pk == task.pk:
        parent_task = None
    if task.parent_task_id == (parent_task.pk if parent_task else None):
        return False
    task.parent_task = parent_task
    if save:
        task.save(update_fields=["parent_task"])
    return True


def _reap_missing_pages(database, client, seen_page_ids, report):
    """Delete tasks whose Notion page has been trashed.

    A trashed page simply stops appearing in query results, and Notion offers no filter to ask about
    trashed rows — so absence from a *full* sweep is the signal. Absence alone is not proof, though
    (a page could be missing for any number of reasons), so each candidate is confirmed by
    retrieving it directly, which still works on trashed pages.
    """
    candidates = NotionTaskLink.objects.filter(database=database).exclude(notion_page_id__in=seen_page_ids)
    for link in candidates.exclude(task=None).select_related("task"):
        try:
            page = client.retrieve_page(link.notion_page_id)
        except Exception:  # noqa: BLE001 - a lookup failure must never delete a task
            logger.exception("Could not confirm Notion page %s; keeping the local task", link.notion_page_id)
            continue
        if not (page.get("in_trash") or page.get("archived")):
            continue
        task_id = link.task_id
        link.task.delete()  # cascades the link's task to NULL; drop the row too
        link.delete()
        report.deleted_locally += 1
        logger.info("Deleted task %s — its Notion page %s was trashed", task_id, link.notion_page_id)


# --------------------------------------------------------------------------------------
# Push: Organizer -> Notion
# --------------------------------------------------------------------------------------
def _push(connection, database, client, names, report):
    # 1. Tombstones: the local task is gone, so trash its page.
    for link in NotionTaskLink.objects.filter(database=database, task=None):
        try:
            client.trash_page(link.notion_page_id)
            report.trashed += 1
        except Exception:  # noqa: BLE001 - a page already gone upstream must not block the run
            logger.exception("Could not trash Notion page %s", link.notion_page_id)
        link.delete()

    # 2. New local tasks. Scoped by owner: Project and Tag are global in this app, so a
    #    project-based filter alone would push other users' tasks into this user's workspace.
    unlinked = (
        TaskItem.objects.filter(owner=connection.user, notion_link__isnull=True).order_by("pk").prefetch_related("tags")
    )
    created_links = []
    for task in unlinked:
        link = _create_page(database, client, names, task, report)
        if link is not None:
            created_links.append(link)

    # 3. Locally-changed linked tasks.
    linked = (
        NotionTaskLink.objects.filter(database=database)
        .exclude(task=None)
        .select_related("task")
        .prefetch_related("task__tags")
    )
    for link in linked:
        task = link.task
        if link.local_changed_at is not None and task.changed_date <= link.local_changed_at:
            continue
        parent_page_id = _parent_page_id(database, task)
        properties = mapping.task_to_properties(task, names, parent_page_id=parent_page_id)
        try:
            page = client.update_page(link.notion_page_id, properties)
        except Exception:  # noqa: BLE001 - one bad page must not abort the batch
            logger.exception("Could not update Notion page %s", link.notion_page_id)
            continue
        report.pushed += 1
        _stamp(link, page_edited=_parse_notion_time(page.get("last_edited_time")), task=task)

    # Only pages created in this run still need their relation: step 3 writes it inline, via
    # task_to_properties, for every task that changed.
    _link_parents(database, client, names, created_links)


def _create_page(database, client, names, task, report):
    """Create the Notion page for ``task``. The parent relation is filled in by a later pass."""
    properties = mapping.task_to_properties(task, names, parent_page_id=None, include_relation=False)
    try:
        page = client.create_page(database.data_source_id, properties)
    except Exception:  # noqa: BLE001 - one bad task must not abort the batch
        logger.exception("Could not create a Notion page for task %s", task.pk)
        return None
    link = NotionTaskLink.objects.create(database=database, task=task, notion_page_id=page["id"])
    _stamp(link, page_edited=_parse_notion_time(page.get("last_edited_time")), task=task)
    report.created_remotely += 1
    return link


def _parent_page_id(database, task):
    if not task.parent_task_id:
        return None
    parent_link = NotionTaskLink.objects.filter(database=database, task_id=task.parent_task_id).first()
    return parent_link.notion_page_id if parent_link else None


def _link_parents(database, client, names, links):
    """Second pass writing parent relations for *newly created* pages.

    Pages are created without their relation, because the parent may not have a page yet when the
    child is created. Only those need this pass: an ordinary update already carries the relation in
    its property payload, so re-patching every child on every run would spend rate limit — and churn
    ``last_edited_time`` — for nothing.
    """
    for link in links:
        if link.task is None or link.task.parent_task_id is None:
            continue
        parent_page_id = _parent_page_id(database, link.task)
        if not parent_page_id:
            continue
        try:
            page = client.update_page(
                link.notion_page_id,
                {names[schema.PARENT_TASK]: {"relation": [{"id": parent_page_id}]}},
            )
        except Exception:  # noqa: BLE001
            logger.exception("Could not link parent for Notion page %s", link.notion_page_id)
            continue
        _stamp(link, page_edited=_parse_notion_time(page.get("last_edited_time")), task=link.task)


# --------------------------------------------------------------------------------------
# Watermarks
# --------------------------------------------------------------------------------------
def _stamp(link, *, page_edited, task):
    """Record where both sides stand after a write.

    This is the ping-pong invariant: ``changed_date`` is ``auto_now``, so any write the sync makes
    bumps it, and without re-stamping here the next run would mistake the sync's own write for a
    user edit and push it back — forever.
    """
    link.notion_last_edited_time = page_edited or link.notion_last_edited_time
    link.local_changed_at = task.changed_date if task is not None else link.local_changed_at
    link.last_synced_at = timezone.now()
    link.save(update_fields=["notion_last_edited_time", "local_changed_at", "last_synced_at"])


def _parse_notion_time(value):
    if not value:
        return None
    parsed = parse_datetime(value)
    if parsed is None:
        return None
    return parsed if timezone.is_aware(parsed) else timezone.make_aware(parsed, UTC)
