"""Translating between ``TaskItem`` and Notion property values.

Because Organizer owns the Notion schema, this is an almost-total mapping rather than the lossy
subset a thinner provider would force. Four hazards make it more than mechanical:

* **Date-only values wipe the time of day.** A Notion date property can hold a datetime, but a user
  who picks a date without a time hands back midnight. Applying that literally would destroy a
  deadline's 14:30. Inbound dates are therefore compared at *date* granularity and only overwrite
  the local value when the calendar date actually moved.
* **``completed_date`` is a ``MonitorField``.** Its ``pre_save`` overwrites whatever you assign with
  ``now()`` the moment ``completed`` flips to True, so a task completed yesterday in Notion would be
  restamped as completed just now. It is written after the fact with ``queryset.update()``.
* **Projects and tags are global in this app** — neither model has an owner. An unrecognised value
  arriving from one user's Notion workspace is therefore ignored and logged, never created, because
  creating it would put it in front of every user of the deployment.
* **``TaskItem.save()`` copies the project's tags onto the task.** So an inbound project change
  legitimately grows the task's tag set, and those tags flow back to Notion on the next push. That
  is the model's behaviour, not a sync bug.
"""

import logging

from django.utils import timezone
from django.utils.dateparse import parse_date, parse_datetime

from integrations.notion import schema
from tasks.models import Project, Tag, TaskItem

logger = logging.getLogger(__name__)

# Notion rejects a single rich-text object longer than this; longer text is split across several.
RICH_TEXT_CHUNK = 2000
# Notion caps a rich-text array at 100 elements, so this is the effective description ceiling.
MAX_RICH_TEXT_CHUNKS = 100


# --------------------------------------------------------------------------------------
# Outbound: TaskItem -> Notion
# --------------------------------------------------------------------------------------
def _rich_text(value):
    """Split text into Notion's ≤2000-character rich-text objects."""
    text = (value or "").strip()
    if not text:
        return []
    chunks = [text[i : i + RICH_TEXT_CHUNK] for i in range(0, len(text), RICH_TEXT_CHUNK)]
    if len(chunks) > MAX_RICH_TEXT_CHUNKS:
        logger.warning(
            "Description too long for Notion (%s chars); sending the first %s characters.",
            len(text),
            MAX_RICH_TEXT_CHUNKS * RICH_TEXT_CHUNK,
        )
        chunks = chunks[:MAX_RICH_TEXT_CHUNKS]
    return [{"type": "text", "text": {"content": chunk}} for chunk in chunks]


def _date_value(value):
    return {"start": value.isoformat()} if value else None


def _select_value(name):
    return {"name": str(name).replace(",", " ")[:100]} if name else None


def task_to_properties(task, names, parent_page_id=None, include_relation=True):
    """Build the Notion ``properties`` payload for ``task``.

    ``names`` maps logical property names to their current Notion titles, so a property the user
    renamed is still written to the right column.
    """
    properties = {
        names[schema.TITLE]: {"title": [{"type": "text", "text": {"content": (task.title or "")[:2000]}}]},
        names[schema.DESCRIPTION]: {"rich_text": _rich_text(task.description)},
        names[schema.STATUS]: {"select": _select_value(schema.status_option_names().get(task.status))},
        names[schema.DONE]: {"checkbox": bool(task.completed)},
        names[schema.COMPLETED_AT]: {"date": _date_value(task.completed_date)},
        names[schema.PRIORITY]: {"select": _select_value(schema.priority_option_names().get(task.priority))},
        names[schema.START]: {"date": _date_value(task.start_date)},
        names[schema.DEADLINE]: {"date": _date_value(task.end_date)},
        names[schema.ESTIMATE]: {"number": task.estimated_time},
        names[schema.TODAY]: {"checkbox": bool(task.for_today)},
        names[schema.TAGS]: {"multi_select": [_select_value(tag.name) for tag in task.tags.all()]},
        names[schema.PROJECT]: {"select": _select_value(task.project.title if task.project else None)},
    }
    if include_relation:
        # An empty list is how a relation is cleared, so this handles "parent removed" too.
        properties[names[schema.PARENT_TASK]] = {"relation": [{"id": parent_page_id}] if parent_page_id else []}
    return properties


# --------------------------------------------------------------------------------------
# Inbound: Notion -> TaskItem
# --------------------------------------------------------------------------------------
def _read(page, names, logical):
    return (page.get("properties") or {}).get(names.get(logical, logical)) or {}


def read_title(page, names):
    parts = _read(page, names, schema.TITLE).get("title") or []
    return "".join(item.get("plain_text", "") for item in parts).strip()


def read_rich_text(page, names, logical):
    parts = _read(page, names, logical).get("rich_text") or []
    return "".join(item.get("plain_text", "") for item in parts).strip()


def read_checkbox(page, names, logical):
    return bool(_read(page, names, logical).get("checkbox"))


def read_number(page, names, logical):
    return _read(page, names, logical).get("number")


def read_select(page, names, logical):
    selected = _read(page, names, logical).get("select")
    return (selected or {}).get("name") or ""


def read_multi_select(page, names, logical):
    return [
        item.get("name", "") for item in (_read(page, names, logical).get("multi_select") or []) if item.get("name")
    ]


def read_relation_ids(page, names, logical):
    return [item.get("id") for item in (_read(page, names, logical).get("relation") or []) if item.get("id")]


def read_datetime(page, names, logical, current):
    """Read a Notion date, preserving a local time-of-day the Notion value cannot express.

    Notion hands back midnight for a date picked without a time. Overwriting a deadline of
    ``2026-07-15T14:30`` with that would silently destroy the time, so the comparison is done at
    date granularity: when the calendar date is unchanged, the existing local value wins.
    """
    raw = (_read(page, names, logical).get("date") or {}).get("start")
    if not raw:
        return None

    parsed = parse_datetime(raw)
    if parsed is None:
        date_only = parse_date(raw)
        if date_only is None:
            return current
        if current is not None and timezone.localtime(current).date() == date_only:
            return current
        # Midnight local time, so a date typed in Notion lands on the day the user meant.
        return timezone.make_aware(
            timezone.datetime.combine(date_only, timezone.datetime.min.time()),
            timezone.get_current_timezone(),
        )

    if timezone.is_naive(parsed):
        parsed = timezone.make_aware(parsed, timezone.get_current_timezone())

    # A value that is midnight and whose date matches what we already have is Notion echoing a
    # date-only edit back at us; keep the finer local time.
    if current is not None and timezone.localtime(parsed).date() == timezone.localtime(current).date():
        local = timezone.localtime(parsed)
        if (local.hour, local.minute, local.second) == (0, 0, 0):
            return current
    return parsed


def status_from_option(option_name, current):
    """Map a Notion Status option back to an Organizer status value."""
    if not option_name:
        return current
    for value, label in TaskItem.TAKSITEM_STATUSES:
        if option_name.strip().casefold() in {label.casefold(), str(value).casefold()}:
            return value
    logger.info("Ignoring unknown Notion status option %r", option_name)
    return current


def priority_from_option(option_name, current):
    if not option_name:
        return current
    for value, label in TaskItem.TASKITEM_PRIORITIES:
        if option_name.strip().casefold() == label.casefold():
            return value
    logger.info("Ignoring unknown Notion priority option %r", option_name)
    return current


def resolve_project(title, current):
    """Match an existing project by title. Never creates one — projects are global."""
    if not title:
        return None
    project = Project.objects.filter(title__iexact=title.strip()).first()
    if project is None:
        logger.info("Ignoring unknown Notion project %r (projects are not created from Notion)", title)
        return current
    return project


def resolve_tags(names_from_notion):
    """Match existing tags by name or slug. Never creates them — tags are global.

    Returns ``(tags, unresolved)``. When *nothing* resolved but Notion did send names, the caller
    keeps the task's current tags rather than clearing them, so an unrecognised set is inert.
    """
    resolved, unresolved = [], []
    for name in names_from_notion:
        cleaned = name.strip()
        if not cleaned:
            continue
        tag = Tag.objects.filter(name__iexact=cleaned).first() or Tag.objects.filter(slug__iexact=cleaned).first()
        if tag is None:
            unresolved.append(cleaned)
        else:
            resolved.append(tag)
    if unresolved:
        logger.info("Ignoring unknown Notion tags %s (tags are not created from Notion)", unresolved)
    return resolved, unresolved


def apply_page_to_task(page, task, names):
    """Copy a Notion page's properties onto ``task`` in memory.

    Returns ``(changed, completed_date)``: ``changed`` is whether anything actually differs (so an
    idempotent re-apply writes nothing), and ``completed_date`` has to be applied after ``save()``
    because ``MonitorField`` would otherwise overwrite it with ``now()``.
    """
    before = _snapshot(task)

    title = read_title(page, names)
    if title:
        task.title = title[:1024]
    task.description = read_rich_text(page, names, schema.DESCRIPTION) or None
    task.status = status_from_option(read_select(page, names, schema.STATUS), task.status)
    task.completed = read_checkbox(page, names, schema.DONE)
    task.priority = priority_from_option(read_select(page, names, schema.PRIORITY), task.priority)
    task.start_date = read_datetime(page, names, schema.START, task.start_date)
    task.end_date = read_datetime(page, names, schema.DEADLINE, task.end_date)
    task.estimated_time = read_number(page, names, schema.ESTIMATE)
    task.for_today = read_checkbox(page, names, schema.TODAY)
    task.project = resolve_project(read_select(page, names, schema.PROJECT), task.project)

    completed_date = read_datetime(page, names, schema.COMPLETED_AT, task.completed_date)
    if not task.completed:
        completed_date = None

    changed = _snapshot(task) != before
    return changed, completed_date


def _snapshot(task):
    """The fields the sync owns, for cheap change detection."""
    return (
        task.title,
        task.description,
        task.status,
        task.completed,
        task.priority,
        task.start_date,
        task.end_date,
        task.estimated_time,
        task.for_today,
        task.project_id,
    )


def apply_completed_date(task, value):
    """Persist ``completed_date`` around ``MonitorField``.

    ``MonitorField.pre_save`` replaces any assigned value with ``now()`` when ``completed`` flips to
    True. A queryset update bypasses ``pre_save`` entirely — and also bypasses ``auto_now`` on
    ``changed_date``, so this correction does not look like a fresh local edit to the next sync.
    """
    if task.completed_date == value:
        return False
    TaskItem.objects.filter(pk=task.pk).update(completed_date=value)
    task.completed_date = value
    return True


def sync_tags(task, names_from_notion):
    """Replace the task's tags with the resolvable subset of what Notion sent.

    An entirely unresolvable set leaves the task's tags alone: better to ignore an unrecognised
    value than to strip tags the user still has in Organizer.
    """
    resolved, unresolved = resolve_tags(names_from_notion)
    if not resolved and unresolved:
        return False
    current = set(task.tags.values_list("pk", flat=True))
    incoming = {tag.pk for tag in resolved}
    if current == incoming:
        return False
    task.tags.set(resolved)
    return True
