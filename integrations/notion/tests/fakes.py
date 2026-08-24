"""An in-memory stand-in for the Notion API.

Deliberately reproduces the behaviours that the sync engine is built around, because those are
exactly what a naive mock would paper over:

* ``last_edited_time`` is **rounded down to the minute**, as Notion does.
* Every write records ``last_edited_by``, defaulting to the integration's own bot — so echo
  suppression is exercised for real, and a "human" edit has to be made explicitly.
* Written property values come back in Notion's *read* shape (``plain_text`` populated), which is
  not the shape they were written in.
* Queries return non-archived rows only, and offer no way to ask about trashed pages.
"""

import itertools
from datetime import timedelta

from django.utils import timezone
from django.utils.dateparse import parse_datetime

BOT_ID = "bot-organizer"
HUMAN_ID = "user-human"


def minute_floor(moment):
    """Notion rounds page timestamps down to the minute."""
    return moment.replace(second=0, microsecond=0)


class FakeNotion:
    """A single data source, its pages, and a controllable clock."""

    def __init__(self, bot_id=BOT_ID, property_titles=None):
        self.bot_id = bot_id
        self.pages = {}
        self.trashed = set()
        self.now = timezone.now().replace(second=0, microsecond=0)
        self._ids = itertools.count(1)
        self.data_source_id = "ds-1"
        self.database_id = "db-1"
        self.property_titles = property_titles or {}
        self.calls = []
        self.fail_next = None

    # -- clock -------------------------------------------------------------------------
    def advance(self, **kwargs):
        self.now = self.now + timedelta(**kwargs)
        return self.now

    def _stamp(self, page, editor):
        page["last_edited_time"] = minute_floor(self.now).isoformat().replace("+00:00", "Z")
        page["last_edited_by"] = {"object": "user", "id": editor}

    # -- test helpers ------------------------------------------------------------------
    def add_page_as_human(self, properties):
        """A page a person created in Notion, as the sync would first see it."""
        page_id = f"page-{next(self._ids)}"
        page = {"id": page_id, "object": "page", "properties": {}, "in_trash": False}
        page["properties"] = _read_shape(properties)
        self._stamp(page, HUMAN_ID)
        self.pages[page_id] = page
        return page

    def edit_as_human(self, page_id, properties):
        page = self.pages[page_id]
        page["properties"].update(_read_shape(properties))
        self._stamp(page, HUMAN_ID)
        return page

    def trash_as_human(self, page_id):
        self.pages[page_id]["in_trash"] = True
        self.trashed.add(page_id)
        self._stamp(self.pages[page_id], HUMAN_ID)

    def live_pages(self):
        return [page for page in self.pages.values() if not page.get("in_trash")]

    # -- the NotionClient interface ----------------------------------------------------
    def retrieve_data_source(self, data_source_id):
        self.calls.append(("retrieve_data_source", data_source_id))
        return {
            "id": data_source_id,
            "properties": {title: {"id": pid, "type": "rich_text"} for title, pid in self.property_titles.items()},
        }

    def update_data_source(self, data_source_id, properties):
        self.calls.append(("update_data_source", data_source_id))
        # Patching in a property makes it show up in later retrieves, as it does in Notion — which
        # is how the parent-task relation joins the schema after the data source exists.
        for name in properties:
            self.property_titles.setdefault(name, f"pid-{len(self.property_titles)}")
        return {"id": data_source_id, "properties": properties}

    def retrieve_database(self, database_id):
        return {"id": database_id, "data_sources": [{"id": self.data_source_id, "name": "Tasks"}]}

    def create_database(self, parent_page_id, title, properties, icon=None):
        self.calls.append(("create_database", parent_page_id))
        self.property_titles = {name: f"pid-{index}" for index, name in enumerate(properties)}
        return {
            "id": self.database_id,
            "data_sources": [{"id": self.data_source_id, "name": title}],
        }

    def search_pages(self, query=""):
        return [
            {"id": "parent-page", "url": "https://notion.so/parent", "properties": {}, "parent": {"type": "workspace"}}
        ]

    def query_data_source(self, data_source_id, *, filter=None, sorts=None):  # noqa: A002 - Notion's name
        self.calls.append(("query", filter))
        results = self.live_pages()
        if filter:
            since = parse_datetime(filter["last_edited_time"]["on_or_after"])
            results = [page for page in results if parse_datetime(page["last_edited_time"]) >= since]
        return sorted(results, key=lambda page: page["last_edited_time"])

    def create_page(self, data_source_id, properties):
        if self.fail_next == "create_page":
            self.fail_next = None
            raise RuntimeError("simulated Notion failure")
        page_id = f"page-{next(self._ids)}"
        page = {"id": page_id, "object": "page", "in_trash": False, "properties": _read_shape(properties)}
        self._stamp(page, self.bot_id)
        self.pages[page_id] = page
        self.calls.append(("create_page", page_id))
        return page

    def retrieve_page(self, page_id):
        self.calls.append(("retrieve_page", page_id))
        if page_id not in self.pages:
            raise RuntimeError(f"no such page {page_id}")
        return self.pages[page_id]

    def update_page(self, page_id, properties):
        page = self.pages[page_id]
        page["properties"].update(_read_shape(properties))
        self._stamp(page, self.bot_id)
        self.calls.append(("update_page", page_id))
        return page

    def trash_page(self, page_id):
        self.calls.append(("trash_page", page_id))
        if page_id in self.pages:
            self.pages[page_id]["in_trash"] = True
            self.trashed.add(page_id)
        return {"id": page_id, "in_trash": True}

    def close(self):
        pass

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


def _read_shape(properties):
    """Convert a write payload into the shape Notion returns on read.

    Notion echoes text back with ``plain_text`` populated, which the write shape does not carry —
    a mock that skipped this would let a broken reader pass.
    """
    out = {}
    for name, value in (properties or {}).items():
        converted = dict(value)
        for key in ("title", "rich_text"):
            if key in converted:
                converted[key] = [
                    {**item, "plain_text": item.get("text", {}).get("content", "")} for item in converted[key] or []
                ]
                converted["type"] = key
        for key in ("select", "checkbox", "date", "number", "multi_select", "relation"):
            if key in converted:
                converted["type"] = key
        out[name] = converted
    return out
