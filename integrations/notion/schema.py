"""The Notion database schema Organizer creates and owns, plus provisioning and drift detection.

Because the sync *creates* its database rather than adapting to one, it authors the schema — which
is why almost every Organizer field gets a real column here instead of the lossy subset a
thinner integration would manage.

Two structural facts drive this module:

* **The parent-task relation cannot be part of the initial schema.** It points at the data source
  being created, whose id does not exist until the create call returns. Provisioning therefore
  creates the database, then patches the self-relation in.
* **Properties are addressed by id, not name.** The ids are recorded at provisioning
  (``NotionDatabase.property_ids``) so a user renaming "Deadline" in Notion does not break mapping.
  A property that *disappears* is a different matter, and pauses the sync (see :func:`check_drift`).
"""

import logging

from django.utils.text import Truncator

from integrations.notion.exceptions import NotionSchemaDriftError
from tasks.models import TaskItem

logger = logging.getLogger(__name__)

DATABASE_TITLE = "Organizer tasks"
DATABASE_ICON = {"type": "emoji", "emoji": "✅"}

# Logical name -> the property title created in Notion. The logical names are what the rest of the
# code refers to; the titles are what the user sees and may rename.
TITLE = "Name"
DESCRIPTION = "Description"
STATUS = "Status"
DONE = "Done"
COMPLETED_AT = "Completed at"
PRIORITY = "Priority"
START = "Start"
DEADLINE = "Deadline"
ESTIMATE = "Estimate (min)"
TODAY = "Today"
TAGS = "Tags"
PROJECT = "Project"
PARENT_TASK = "Parent task"
LAST_EDITED_BY = "Last edited by"

# Properties the sync reads or writes. Losing any of these is schema drift; `Last edited by` is
# deliberately absent because it is cosmetic (see below).
REQUIRED_PROPERTIES = (
    TITLE,
    DESCRIPTION,
    STATUS,
    DONE,
    COMPLETED_AT,
    PRIORITY,
    START,
    DEADLINE,
    ESTIMATE,
    TODAY,
    TAGS,
    PROJECT,
    PARENT_TASK,
)

# Notion's fixed select-option palette.
NOTION_COLORS = ("default", "gray", "brown", "orange", "yellow", "green", "blue", "purple", "pink", "red")

# Approximate RGB anchors for each palette entry, used to place a Tag's hex colour.
_COLOR_ANCHORS = {
    "gray": (155, 155, 155),
    "brown": (140, 100, 80),
    "orange": (217, 133, 59),
    "yellow": (223, 171, 1),
    "green": (68, 131, 97),
    "blue": (51, 126, 169),
    "purple": (144, 101, 176),
    "pink": (193, 76, 138),
    "red": (212, 76, 71),
}

_STATUS_COLORS = {
    TaskItem.IDEA: "gray",
    TaskItem.BLOCKED: "red",
    TaskItem.IN_PROGRESS: "blue",
    TaskItem.GIVEN_UP: "brown",
}
_PRIORITY_COLORS = {TaskItem.HIGH: "red", TaskItem.NORMAL: "default", TaskItem.LOW: "gray"}


def status_option_names():
    """Notion option name per Organizer status, using the labels the app itself shows."""
    return {value: label for value, label in TaskItem.TAKSITEM_STATUSES}


def priority_option_names():
    return {value: label for value, label in TaskItem.TASKITEM_PRIORITIES}


def nearest_notion_color(hex_color):
    """Place a ``Tag.color`` hex string on Notion's fixed palette by nearest RGB anchor."""
    value = (hex_color or "").strip().lstrip("#")
    if len(value) == 3:
        value = "".join(char * 2 for char in value)
    if len(value) != 6:
        return "default"
    try:
        rgb = tuple(int(value[i : i + 2], 16) for i in (0, 2, 4))
    except ValueError:
        return "default"
    # Near-white reads as "no colour chosen" (it is the model default), so keep Notion's default.
    if min(rgb) > 235:
        return "default"
    return min(
        _COLOR_ANCHORS,
        key=lambda name: sum((a - b) ** 2 for a, b in zip(_COLOR_ANCHORS[name], rgb, strict=True)),
    )


def _option(name, color="default"):
    # Notion rejects commas in option names outright, and dedupes case-insensitively.
    return {"name": str(name).replace(",", " ")[:100], "color": color}


def initial_properties():
    """The schema passed to ``create_database``.

    Excludes the parent-task relation, which cannot reference a data source that does not exist yet.
    """
    return {
        TITLE: {"title": {}},
        DESCRIPTION: {"rich_text": {}},
        STATUS: {
            "select": {
                "options": [
                    _option(label, _STATUS_COLORS.get(value, "default")) for value, label in TaskItem.TAKSITEM_STATUSES
                ]
            }
        },
        DONE: {"checkbox": {}},
        COMPLETED_AT: {"date": {}},
        PRIORITY: {
            "select": {
                "options": [
                    _option(label, _PRIORITY_COLORS.get(value, "default"))
                    for value, label in TaskItem.TASKITEM_PRIORITIES
                ]
            }
        },
        START: {"date": {}},
        DEADLINE: {"date": {}},
        ESTIMATE: {"number": {}},
        TODAY: {"checkbox": {}},
        TAGS: {"multi_select": {"options": []}},
        PROJECT: {"select": {"options": []}},
        # Cosmetic only: it shows the user whether a row was last touched by them or by Organizer.
        # Echo suppression does NOT read this property — it reads the page object's own
        # `last_edited_by` field, which is always present regardless of the schema.
        LAST_EDITED_BY: {"last_edited_by": {}},
    }


def self_relation_property(data_source_id):
    """The parent-task relation, patched in once the data source id is known."""
    return {
        PARENT_TASK: {
            "relation": {
                "data_source_id": data_source_id,
                "type": "single_property",
                "single_property": {},
            }
        }
    }


def option_seed_properties(user):
    """Select/multi-select options seeded before bootstrap, from the user's own projects and tags.

    Notion creates an option implicitly when a page first uses it, but seeding up front lets tags
    carry their Organizer colour instead of whatever Notion picks.
    """
    from tasks.models import Project, Tag

    project_titles = (
        Project.objects.filter(tasks__owner=user).distinct().order_by("title").values_list("title", flat=True)
    )
    tags = Tag.objects.filter(tasks__owner=user).distinct().order_by("name")

    return {
        PROJECT: {"select": {"options": [_option(title) for title in project_titles if title]}},
        TAGS: {"multi_select": {"options": [_option(tag.name, nearest_notion_color(tag.color)) for tag in tags]}},
    }


def extract_property_ids(data_source):
    """Map logical property name -> Notion property id, from a retrieved data source."""
    return {name: definition.get("id", "") for name, definition in (data_source.get("properties") or {}).items()}


def check_drift(data_source, property_ids):
    """Raise if a property the sync depends on has disappeared.

    Renames are fine — the recorded ids still resolve. A deletion is not, and pauses the sync rather
    than letting the field silently stop syncing.
    """
    live_ids = {definition.get("id") for definition in (data_source.get("properties") or {}).values()}
    missing = [name for name in REQUIRED_PROPERTIES if property_ids.get(name) not in live_ids]
    if missing:
        raise NotionSchemaDriftError("These properties no longer exist in the Notion database: " + ", ".join(missing))
    return True


def resolve_property_names(data_source, property_ids):
    """Current Notion property *titles*, keyed by our logical names.

    Reading and writing both go through titles (Notion keys ``properties`` by title), so a renamed
    property is followed by resolving its recorded id back to whatever it is called now.
    """
    by_id = {definition.get("id"): name for name, definition in (data_source.get("properties") or {}).items()}
    return {logical: by_id.get(property_ids.get(logical), logical) for logical in property_ids}


def provision(client, connection, parent_page_id):
    """Create the task database under ``parent_page_id`` and record what the sync needs.

    Returns an unsaved :class:`~integrations.notion.models.NotionDatabase`; the caller saves it, so
    provisioning and its follow-up option seeding happen in one transaction.
    """
    from integrations.notion.models import NotionDatabase

    created = client.create_database(parent_page_id, DATABASE_TITLE, initial_properties(), icon=DATABASE_ICON)
    database_id = created["id"]

    # 2025-09-03 returns the data source inline; fall back to a retrieve for safety.
    data_sources = created.get("data_sources") or []
    if data_sources:
        data_source_id = data_sources[0]["id"]
    else:
        data_source_id = client.retrieve_database(database_id)["data_sources"][0]["id"]

    # Now that the data source exists, it can point at itself.
    client.update_data_source(data_source_id, self_relation_property(data_source_id))
    client.update_data_source(data_source_id, option_seed_properties(connection.user))

    data_source = client.retrieve_data_source(data_source_id)

    logger.info("Provisioned Notion database %s for %s", database_id, connection.user)
    return NotionDatabase(
        connection=connection,
        database_id=database_id,
        data_source_id=data_source_id,
        parent_page_id=parent_page_id,
        property_ids=extract_property_ids(data_source),
    )


def page_title(page):
    """Best-effort human label for a Notion page, for the parent-page picker."""
    properties = page.get("properties") or {}
    for definition in properties.values():
        if definition.get("type") == "title":
            parts = [item.get("plain_text", "") for item in definition.get("title") or []]
            joined = "".join(parts).strip()
            if joined:
                return Truncator(joined).chars(120)
    return "Untitled"
