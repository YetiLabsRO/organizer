"""The two-way VolunHub sync engine.

One run, per connection: **list** → **merge each task** → **detect removals**.

VolunHub gives a sync client very little to work with, and the design follows from that:

* ``changed_date`` is not bumped by workflow transitions or (un)assignment, the listing's
  ``completed`` column is stale, and there is no changed-since filter, no tombstone and no webhook.
  So every run reads the user's **complete** assigned-task listing, and change detection is by
  **value**, not by timestamp.

* **Three-way merge against a snapshot.** Each link stores the last values both sides agreed on.
  Per field: changed only in VolunHub → applied locally; changed only locally → pushed; changed on
  both sides to different values → **Organizer wins** (VolunHub offers no trustworthy change time to
  arbitrate with). A field we cannot push right now (read-only grant, content push disabled) gives
  way to VolunHub instead. A local ``givenup`` status is the one exception: never pushed, never
  overwritten.

* **Echo suppression is free.** Whatever we push becomes the new snapshot, so the next run sees
  VolunHub equal to the snapshot and does nothing. Unlike the Notion sync there is no watermark to
  re-stamp: our own ``save()`` bumping ``changed_date`` is harmless because nothing here reads it.

* **Removal is inferred, carefully.** A linked task missing from a complete listing is looked up by
  id: 404 → deleted, 200 → unassigned. Either way the local task is kept and only marked; anything
  else leaves it alone. A partial listing aborts the run before anything is merged or removed.

* **Never create or delete upstream.** Local creates stay local; a local delete leaves a tombstone
  link so the task is not re-imported, and nothing is deleted in VolunHub.
"""

import logging
from datetime import timedelta

from django.db import transaction
from django.utils import timezone

from integrations.volunhub import mapping
from integrations.volunhub.client import VolunHubAPI
from integrations.volunhub.exceptions import VolunHubAPIError, VolunHubAuthError, VolunHubError
from integrations.volunhub.locks import sync_lock
from integrations.volunhub.models import VolunHubConnection, VolunHubTaskLink
from integrations.volunhub.projects import resolve_project
from tasks.models import TaskItem
from tasks.signals import broadcast_task_updated

logger = logging.getLogger(__name__)

NOOP, AGREE, APPLY, PUSH, KEEP = "noop", "agree", "apply", "push", "keep"


class SyncReport:
    """What one run did — returned to the caller and logged; nothing depends on its shape."""

    def __init__(self):
        self.listed = 0
        self.created_locally = 0
        self.updated_locally = 0
        self.pushed = 0
        self.conflicts = 0
        self.removed = 0
        self.reattached = 0
        self.errors = 0
        self.skipped = False

    def as_dict(self):
        return self.__dict__.copy()

    def __str__(self):
        return ", ".join(f"{key}={value}" for key, value in self.__dict__.items() if value)


def sync_connection(connection, *, api=None):
    """Synchronize one connection. Returns a :class:`SyncReport`.

    Auth problems become a connection *status* rather than an exception, so one broken connection
    never aborts a scheduled batch. At most one run per connection executes at a time; a run that
    finds another in progress is skipped, not queued.
    """
    report = SyncReport()
    if connection.status == VolunHubConnection.NEEDS_REAUTH:
        return report

    with sync_lock(connection.pk) as acquired:
        if not acquired:
            report.skipped = True
            logger.info("VolunHub sync for %s already running; skipped", connection.user)
            return report

        owns_api = api is None
        api = api or VolunHubAPI(connection)
        try:
            remote_tasks = api.list_assigned_tasks()
            report.listed = len(remote_tasks)
            _sync_tasks(connection, api, remote_tasks, report)
            _detect_removals(connection, api, {int(remote["id"]) for remote in remote_tasks}, report)

            connection.last_synced_at = timezone.now()
            fields = ["last_synced_at"]
            if connection.content_push_enabled and connection.last_error:
                # A disabled content push keeps its reason on display; anything else is now stale.
                connection.last_error = ""
                fields.append("last_error")
            connection.save(update_fields=fields)
            logger.info("VolunHub sync for %s: %s", connection.user, report or "no changes")
        except VolunHubAuthError as exc:
            # refresh_access_token / mark_needs_reauth already recorded the status.
            logger.warning("VolunHub auth failed for %s: %s", connection.user, exc)
        except VolunHubError as exc:
            connection.last_error = str(exc)
            connection.save(update_fields=["last_error"])
            logger.warning("VolunHub sync failed for %s: %s", connection.user, exc)
        finally:
            if owns_api:
                api.close()
    return report


# --------------------------------------------------------------------------------------
# Per task
# --------------------------------------------------------------------------------------
def _sync_tasks(connection, api, remote_tasks, report):
    links = {
        link.external_id: link
        for link in VolunHubTaskLink.objects.filter(user=connection.user).select_related("task", "task__project")
    }
    project_cache = {}
    for remote in remote_tasks:
        external_id = int(remote["id"])
        link = links.get(external_id)
        try:
            if link is None:
                _import(connection, remote, project_cache, report)
            elif link.is_tombstone:
                continue  # deleted locally: never re-imported, never deleted upstream
            else:
                _backfill_dates(link.task, remote)
                _merge(connection, api, link, remote, project_cache, report)
        except VolunHubAuthError:
            raise
        except VolunHubAPIError as exc:
            report.errors += 1
            logger.warning("VolunHub task %s failed for %s: %s", external_id, connection.user, exc)
            if link is not None:
                link.last_error = str(exc)
                link.save(update_fields=["last_error"])


def _import(connection, remote, project_cache, report):
    """A VolunHub task we have not seen: create the local task and its link in one transaction."""
    values = mapping.remote_values(remote)
    ref = mapping.project_ref(remote)

    task = TaskItem(owner=connection.user)
    mapping.apply_to_task(task, values)
    task.project = resolve_project(ref, project_cache)

    created_at, changed_at = mapping.remote_timestamps(remote)
    with transaction.atomic():
        task.save()
        # auto_now_add / auto_now would date the task to the import, lumping every imported task
        # together in the list (ordered by changed_date) and in the statistics (by created_date).
        # A queryset update bypasses both, and the WebSocket payload is read after commit, so it
        # carries these dates too.
        dates = {"created_date": created_at or task.created_date, "changed_date": changed_at or task.changed_date}
        if task.completed:
            # MonitorField stamps completed_date with "now", which would pile every historical task
            # onto the import day in the statistics. The last change in VolunHub is the closest
            # thing to a completion time it exposes.
            dates["completed_date"] = changed_at or timezone.now()
        TaskItem.objects.filter(pk=task.pk).update(**dates)
        # Same transaction as the task, so the Notion push never sees it unlinked.
        VolunHubTaskLink.objects.create(
            user=connection.user,
            external_id=int(remote["id"]),
            task=task,
            snapshot=values,
            external_project_id=ref[0] if ref else None,
            last_synced_at=timezone.now(),
        )
    report.created_locally += 1


# A task imported before VolunHub's dates were copied has created_date ≈ changed_date ≈ import time.
# Within this gap it was never edited afterwards, so its changed_date can safely take VolunHub's.
_UNTOUCHED_SINCE_IMPORT = timedelta(minutes=2)


def _backfill_dates(task, remote):
    """Give a task imported before dates were copied VolunHub's created/changed dates. Idempotent.

    ``created_date`` differing from VolunHub's is the marker — once fixed it never differs again.
    ``changed_date`` is only moved when nothing has touched the task since its import, so a real
    later edit (here or applied from VolunHub) keeps its place at the top of the list.
    """
    created_at, changed_at = mapping.remote_timestamps(remote)
    if created_at is None or task.created_date == created_at:
        return
    dates = {"created_date": created_at}
    if changed_at is not None and task.changed_date - task.created_date < _UNTOUCHED_SINCE_IMPORT:
        dates["changed_date"] = changed_at
    TaskItem.objects.filter(pk=task.pk).update(**dates)
    for field, value in dates.items():
        setattr(task, field, value)
    broadcast_task_updated(task)


def _decide(base, remote, local, *, can_push):
    """Three-way decision for one field. Returns ``(action, is_conflict)``."""
    remote_changed, local_changed = remote != base, local != base
    if not remote_changed and not local_changed:
        return NOOP, False
    if remote == local:
        return AGREE, False
    if local_changed and can_push:
        return PUSH, remote_changed  # Organizer wins a true conflict
    if remote_changed:
        return APPLY, local_changed  # we cannot push this field, so VolunHub wins
    return KEEP, False  # local edit we cannot push; kept until VolunHub changes the field


def _merge(connection, api, link, remote, project_cache, report):
    task = link.task
    external_id = link.external_id
    base = link.snapshot or {}
    remote_v = mapping.remote_values(remote)
    local_v = mapping.local_values(task)

    reattached = link.state == VolunHubTaskLink.REMOVED
    if reattached:
        link.reattach()
        report.reattached += 1

    new_base = dict(base)
    apply_local, push_content, push_state = {}, {}, None
    conflicts = 0

    for field in mapping.CONTENT_FIELDS:
        action, conflict = _decide(base.get(field), remote_v[field], local_v[field], can_push=connection.pushes_content)
        conflicts += conflict
        if action in (AGREE, APPLY):
            new_base[field] = remote_v[field]
        if action == APPLY:
            apply_local[field] = remote_v[field]
        elif action == PUSH:
            push_content[field] = local_v[field]

    remote_state, local_state = remote_v[mapping.STATE], local_v[mapping.STATE]
    if remote_state is None:
        new_base[mapping.STATE] = None  # no workflow in VolunHub: status is not synced either way
    elif local_state != mapping.GIVEN_UP:
        action, conflict = _decide(base.get(mapping.STATE), remote_state, local_state, can_push=connection.can_write)
        conflicts += conflict
        if action in (AGREE, APPLY):
            new_base[mapping.STATE] = remote_state
        if action == APPLY:
            apply_local[mapping.STATE] = remote_state
        elif action == PUSH:
            push_state = local_state
    new_base[mapping.RAW_STATE] = remote_v[mapping.RAW_STATE]

    # Project membership is import-only: follow VolunHub when *its* project changes, otherwise leave
    # whatever the user did locally alone. Resolving also keeps auto-created projects' names current.
    ref = mapping.project_ref(remote)
    project = resolve_project(ref, project_cache)
    external_project_id = ref[0] if ref else None
    project_changed = external_project_id != link.external_project_id
    if project_changed:
        task.project = project
        link.external_project_id = external_project_id

    if conflicts:
        report.conflicts += conflicts
        logger.info("VolunHub task %s: %s conflicting field(s), kept Organizer's values", external_id, conflicts)

    if apply_local or project_changed:
        mapping.apply_to_task(task, apply_local)
        task.save()
        report.updated_locally += 1
    elif reattached:
        broadcast_task_updated(task)  # only the badge changed

    errors = []
    if push_content:
        try:
            api.patch_task(external_id, mapping.to_remote_payload(push_content))
        except VolunHubAuthError:
            raise
        except VolunHubAPIError as exc:
            if exc.status_code == 403:
                # Assignees always pass VolunHub's edit check, so a 403 on a task in the user's own
                # list is policy: VolunHub no longer accepts content writes from this token.
                connection.disable_content_push(
                    "VolunHub refused a content update (403); only status changes are sent now."
                )
                logger.warning("VolunHub refused content PATCH for %s; content push disabled", connection.user)
            else:
                errors.append(f"Content not saved in VolunHub: {exc}")
        else:
            new_base.update(push_content)
            report.pushed += 1

    if push_state is not None:
        current = remote_v[mapping.RAW_STATE]
        try:
            for step in mapping.route(current, push_state):
                api.set_state(external_id, step)
                current = step
        except VolunHubAuthError:
            raise
        except VolunHubAPIError as exc:
            errors.append(f"Status not changed in VolunHub ({exc.status_code}): {exc}")
        else:
            new_base[mapping.STATE] = push_state
            report.pushed += 1
        new_base[mapping.RAW_STATE] = current

    if errors:
        report.errors += 1
    link.snapshot = new_base
    link.last_error = "; ".join(errors)
    link.last_synced_at = timezone.now()
    link.save()


# --------------------------------------------------------------------------------------
# Removals
# --------------------------------------------------------------------------------------
def _detect_removals(connection, api, seen_ids, report):
    """Mark linked tasks that left the (complete) listing; drop tombstones that left it too."""
    missing = (
        VolunHubTaskLink.objects.filter(user=connection.user, state=VolunHubTaskLink.ACTIVE, task__isnull=False)
        .exclude(external_id__in=seen_ids)
        .select_related("task")
    )
    for link in missing:
        try:
            remote = api.get_task(link.external_id)
        except VolunHubAuthError:
            raise
        except VolunHubAPIError as exc:
            # Not proof of anything — look again next run.
            logger.info("Could not confirm removal of VolunHub task %s: %s", link.external_id, exc)
            continue
        link.mark_removed(VolunHubTaskLink.DELETED if remote is None else VolunHubTaskLink.UNASSIGNED)
        broadcast_task_updated(link.task)
        report.removed += 1

    VolunHubTaskLink.objects.filter(user=connection.user, task__isnull=True).exclude(external_id__in=seen_ids).delete()
