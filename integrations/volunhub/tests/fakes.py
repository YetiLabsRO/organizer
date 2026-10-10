"""An in-memory stand-in for VolunHub's confined task API.

Deliberately reproduces the quirks the sync engine is built around, because a naive mock would
paper over exactly those:

* The workflow is the real one (``mapping.TRANSITIONS``): an unreachable target answers 409, and a
  same-state request is an idempotent success.
* Status changes do **not** touch ``changed_date`` and do **not** update the ``completed`` column,
  which therefore goes stale — just like ``transition_task`` in VolunHub.
* Datetimes are rendered in ``+03:00`` (Europe/Bucharest), with microseconds dropped when zero.
* The listing holds only *assigned* tasks, ordered by id, paginated at 50.
"""

import itertools
from datetime import UTC, datetime, timedelta, timezone

from django.utils.dateparse import parse_datetime

from integrations.volunhub import mapping
from integrations.volunhub.exceptions import VolunHubAPIError

BUCHAREST = timezone(timedelta(hours=3))
LABELS = {slug: label for label, slug in mapping.STATE_LABELS.items()}
PAGE_SIZE = 50


def bucharest(value):
    """Render an aware datetime (or ISO string) the way VolunHub's API does."""
    if value is None:
        return None
    if isinstance(value, str):
        value = parse_datetime(value)
    return value.astimezone(BUCHAREST).isoformat()


class FakeVolunHub:
    def __init__(self):
        self.tasks = {}
        self.assigned = set()
        self.calls = []
        self._ids = itertools.count(101)
        self.now = datetime(2026, 10, 1, 9, 0, tzinfo=UTC)
        # Failure switches.
        self.fail_listing = False
        self.forbid_patch = False
        self.lookup_error = False
        # States VolunHub refuses to enter (409), simulating a workflow that drifted from ours.
        self.refuse_states = set()

    # -- test helpers ------------------------------------------------------------------
    def add_task(self, *, assigned=True, state="draft", project=None, created=None, **fields):
        """A task as it exists in VolunHub. ``project`` is ``(id, slug, name)`` or None."""
        task_id = next(self._ids)
        task = {
            "id": task_id,
            "title": fields.pop("title", f"Task {task_id}"),
            "description": fields.pop("description", ""),
            "kind": "general",
            "start_date": fields.pop("start_date", None),
            "end_date": fields.pop("end_date", None),
            "deadline": fields.pop("deadline", None),
            "estimated_time": fields.pop("estimated_time", None),
            "actual_time": None,
            "priority": fields.pop("priority", 2),
            "completed": False,  # stale on purpose: transitions never write it
            "state": state,
            "project": project,
            "changed_date": fields.pop("changed", None) or self.now,
            "created_date": created or self.now,
        }
        assert not fields, f"unknown fields {fields}"
        self.tasks[task_id] = task
        if assigned:
            self.assigned.add(task_id)
        return task_id

    def edit(self, task_id, **fields):
        """A person editing the task in VolunHub: content edits bump changed_date."""
        self.tasks[task_id].update(fields)
        self.now += timedelta(minutes=1)
        self.tasks[task_id]["changed_date"] = self.now

    def transition(self, task_id, state):
        """A person moving the task in VolunHub's workflow: changed_date is NOT bumped."""
        self.tasks[task_id]["state"] = state

    def delete(self, task_id):
        self.tasks.pop(task_id)
        self.assigned.discard(task_id)

    def unassign(self, task_id):
        self.assigned.discard(task_id)

    def serialize(self, task_id):
        task = self.tasks[task_id]
        project = task["project"]
        return {
            "id": task["id"],
            "title": task["title"],
            "description": task["description"],
            "kind": task["kind"],
            "start_date": bucharest(task["start_date"]),
            "end_date": bucharest(task["end_date"]),
            "deadline": bucharest(task["deadline"]),
            "estimated_time": task["estimated_time"],
            "actual_time": task["actual_time"],
            "completed": task["completed"],
            "priority": task["priority"],
            "priority_name": {1: "Joasă", 2: "Normală", 3: "Înaltă"}[task["priority"]],
            "state_name": LABELS.get(task["state"], ""),
            "project_id": project[0] if project else None,
            "project_slug": project[1] if project else None,
            "project_name": project[2] if project else None,
            "created_date": bucharest(task["created_date"]),
            "changed_date": bucharest(task["changed_date"]),
        }

    def calls_of(self, name):
        return [call for call in self.calls if call[0] == name]

    # -- the VolunHubAPI interface -----------------------------------------------------
    def list_assigned_tasks(self):
        self.calls.append(("list",))
        if self.fail_listing:
            raise VolunHubAPIError("VolunHub is unavailable (502).", status_code=502)
        return [self.serialize(task_id) for task_id in sorted(self.assigned)]

    def get_task(self, task_id):
        self.calls.append(("get", task_id))
        if self.lookup_error:
            raise VolunHubAPIError("VolunHub is unavailable (503).", status_code=503)
        return self.serialize(task_id) if task_id in self.tasks else None

    def patch_task(self, task_id, fields):
        self.calls.append(("patch", task_id, dict(fields)))
        if self.forbid_patch:
            raise VolunHubAPIError("Acest token nu are acces la această resursă.", status_code=403)
        allowed = {"title", "description", "start_date", "deadline", "estimated_time", "priority"}
        unexpected = set(fields) - allowed
        if unexpected:
            raise AssertionError(f"PATCH carried fields VolunHub would not accept: {unexpected}")
        for key, value in fields.items():
            self.tasks[task_id][key] = parse_datetime(value) if key in ("start_date", "deadline") and value else value
        self.now += timedelta(minutes=1)
        self.tasks[task_id]["changed_date"] = self.now
        return self.serialize(task_id)

    def set_state(self, task_id, state):
        self.calls.append(("status", task_id, state))
        task = self.tasks[task_id]
        current = task["state"]
        if current == state:
            return {"ok": True, "task_id": task_id, "state_name": LABELS[state]}
        if state in self.refuse_states or state not in mapping.TRANSITIONS.get(current, ()):
            raise VolunHubAPIError(f"Cannot go from {current} to {state}", status_code=409)
        task["state"] = state
        return {"ok": True, "task_id": task_id, "state_name": LABELS[state], "completed": state == "finished"}

    def close(self):
        pass
