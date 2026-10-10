"""TaskItem ⇄ VolunHub task, in both directions.

Everything is compared in one shared **Organizer representation** — plain JSON values, so the same
dict can be stored as a link's snapshot. Comparing like with like is what keeps the merge honest:

* VolunHub's ``draft`` and ``planned`` both mean ``idea`` here, so a task sitting in ``draft`` is
  not mistaken for a local change just because ``idea`` would be pushed back as ``planned``.
* Datetimes arrive as ISO-8601 in ``Europe/Bucharest`` (``+03:00``, microseconds dropped when
  zero) and are stored here in UTC; both become the same UTC ISO string, so a timezone-only
  difference is never a change.
* Blank descriptions (``None`` vs ``""``) and line endings are normalized away.

Status comes from VolunHub's workflow state. The listing's ``completed`` column is ignored: VolunHub
transitions never write it, so it goes stale. The state is read from ``state`` when VolunHub sends
the slug, else parsed from the Romanian ``state_name`` label.
"""

from datetime import UTC

from django.utils.dateparse import parse_datetime

from tasks.models import TaskItem

CONTENT_FIELDS = ("title", "description", "start_date", "end_date", "estimated_time", "priority")
STATE = "state"
# The actual VolunHub state (draft included), kept beside the snapshot for route planning.
RAW_STATE = "raw_state"

DRAFT, PLANNED, IN_PROGRESS, FINISHED, BLOCKED = "draft", "planned", "in_progress", "finished", "blocked"
STATES = (DRAFT, PLANNED, IN_PROGRESS, FINISHED, BLOCKED)
STATE_LABELS = {
    "Ciornă": DRAFT,
    "Planificat": PLANNED,
    "În lucru": IN_PROGRESS,
    "Finalizat": FINISHED,
    "Blocat": BLOCKED,
}
# A local status VolunHub has no equivalent for. Never pushed, never overwritten.
GIVEN_UP = "givenup"

# VolunHub's workflow (projects/states/task_flow.py). Used only to plan a route; VolunHub stays the
# authority and answers 409 if this ever drifts.
TRANSITIONS = {
    DRAFT: {PLANNED, BLOCKED, FINISHED},
    PLANNED: {IN_PROGRESS, BLOCKED, FINISHED},
    IN_PROGRESS: {FINISHED, BLOCKED, PLANNED},
    FINISHED: {PLANNED},
    BLOCKED: {DRAFT, PLANNED, IN_PROGRESS, FINISHED},
}

# VolunHub priority 1 Joasă / 2 Normală / 3 Înaltă  <->  Organizer LOW=1 / NORMAL=2 / HIGH=4
PRIORITY_FROM_REMOTE = {1: TaskItem.LOW, 2: TaskItem.NORMAL, 3: TaskItem.HIGH}
PRIORITY_TO_REMOTE = {value: key for key, value in PRIORITY_FROM_REMOTE.items()}

TITLE_MAX = 1024


# --------------------------------------------------------------------------------------
# Normalizers
# --------------------------------------------------------------------------------------
def _text(value):
    return (value or "").replace("\r\n", "\n")


def _datetime_repr(value):
    """A datetime (or ISO string) as a UTC ISO string; None stays None."""
    if not value:
        return None
    if isinstance(value, str):
        parsed = parse_datetime(value)
        if parsed is None:
            return None
        value = parsed
    if value.tzinfo is None:
        value = value.replace(tzinfo=UTC)
    return value.astimezone(UTC).isoformat()


def _int_or_none(value):
    try:
        return int(value) if value is not None and value != "" else None
    except (TypeError, ValueError):
        return None


# --------------------------------------------------------------------------------------
# State
# --------------------------------------------------------------------------------------
def remote_state(remote):
    """The VolunHub state slug, or None when the task has no workflow (or an unknown label)."""
    slug = remote.get("state")
    if isinstance(slug, str) and slug in STATES:
        return slug
    return STATE_LABELS.get((remote.get("state_name") or "").strip())


def collapse(state):
    """VolunHub state -> comparison value. ``draft`` reads as ``planned`` (both are ``idea``)."""
    if state is None:
        return None
    return PLANNED if state == DRAFT else state


def local_state(task):
    if task.completed:
        return FINISHED
    return {
        TaskItem.IN_PROGRESS: IN_PROGRESS,
        TaskItem.BLOCKED: BLOCKED,
        TaskItem.GIVEN_UP: GIVEN_UP,
    }.get(task.status, PLANNED)


def route(current, target):
    """The VolunHub states to request, in order, to get from ``current`` to ``target``.

    ``planned`` is reachable from every state but itself and reaches every state we push, so it is
    the one detour ever needed (draft → in_progress, finished → in_progress / blocked).
    """
    if current == target:
        return []
    if current is None or target in TRANSITIONS.get(current, ()):
        return [target]
    return [PLANNED, target] if target != PLANNED else [PLANNED]


# --------------------------------------------------------------------------------------
# Both sides -> Organizer representation
# --------------------------------------------------------------------------------------
def remote_values(remote):
    raw = remote_state(remote)
    return {
        "title": (remote.get("title") or "")[:TITLE_MAX],
        "description": _text(remote.get("description")),
        "start_date": _datetime_repr(remote.get("start_date")),
        # Organizer's end_date is its deadline; VolunHub's end_date is a work window and stays unmapped.
        "end_date": _datetime_repr(remote.get("deadline")),
        "estimated_time": _int_or_none(remote.get("estimated_time")),
        "priority": PRIORITY_FROM_REMOTE.get(_int_or_none(remote.get("priority")), TaskItem.NORMAL),
        STATE: collapse(raw),
        RAW_STATE: raw,
    }


def local_values(task):
    return {
        "title": task.title or "",
        "description": _text(task.description),
        "start_date": _datetime_repr(task.start_date),
        "end_date": _datetime_repr(task.end_date),
        "estimated_time": task.estimated_time,
        "priority": task.priority,
        STATE: local_state(task),
    }


# --------------------------------------------------------------------------------------
# Organizer representation -> each side
# --------------------------------------------------------------------------------------
def apply_to_task(task, values):
    """Assign represented ``values`` onto ``task`` (unsaved). Only keys present are touched."""
    for field in ("title", "description", "estimated_time", "priority"):
        if field in values:
            setattr(task, field, values[field])
    for field in ("start_date", "end_date"):
        if field in values:
            setattr(task, field, parse_datetime(values[field]) if values[field] else None)
    if STATE in values and values[STATE] not in (None, GIVEN_UP):
        state = values[STATE]
        if state == FINISHED:
            task.completed = True
        else:
            task.completed = False
            task.status = {IN_PROGRESS: TaskItem.IN_PROGRESS, BLOCKED: TaskItem.BLOCKED}.get(state, TaskItem.IDEA)


def to_remote_payload(values):
    """The PATCH body for the content fields in ``values``."""
    payload = {}
    for field in ("title", "description", "start_date", "estimated_time"):
        if field in values:
            payload[field] = values[field]
    if "end_date" in values:
        payload["deadline"] = values["end_date"]
    if "priority" in values:
        payload["priority"] = PRIORITY_TO_REMOTE.get(values["priority"], 2)
    return payload


def project_ref(remote):
    """``(id, slug, name)`` of the task's VolunHub project, or None for a standalone task."""
    project_id = _int_or_none(remote.get("project_id"))
    if project_id is None:
        return None
    return project_id, remote.get("project_slug") or "", remote.get("project_name") or ""


def remote_timestamps(remote):
    """VolunHub's ``(created_date, changed_date)`` as aware datetimes (either may be None).

    Not synced fields — they are copied onto an imported task so it sorts and counts by when it was
    created and last changed in VolunHub, not by when Organizer happened to import it.
    """
    created = parse_datetime(remote.get("created_date") or "")
    changed = parse_datetime(remote.get("changed_date") or "")
    if created is not None and changed is not None and changed < created:
        changed = created
    return created, changed
