# Change: Recurring task templates

## Why
Some tasks recur on a fixed cadence — e.g. "prepare the monthly financial documents" on the 1st of
every month. Today the user re-creates these by hand each period. There is no way to define a
task once and have the system materialize it automatically on schedule. This change adds
**task templates** (a reusable blueprint + a recurrence rule) and a scheduler that generates real
`TaskItem`s from them.

## What Changes
- Add a **`TaskTemplate`** model: a task blueprint (title, description, priority, estimated time,
  project, tags, owner) plus a **structured recurrence rule** (frequency daily/weekly/monthly/yearly,
  interval N, day-of-month, weekdays, optional start/end dates) and generation controls
  (`lead_time_days`, `skip_if_previous_open`, `is_active`, `last_generated_occurrence`).
- Reserve a nullable `rrule` column so the generator can migrate to full iCal RRULE later without a
  breaking schema change (**structured now, RRULE-ready**).
- Add a **generation engine**: a pure `materialize_due_tasks()` core, invoked by a **Celery beat**
  periodic task (daily) and also exposed as a `generate_recurring_tasks` management command for
  manual/CI runs. Generation is **idempotent** and creates **at most one task per template per run**
  for the **most recent due occurrence** (latest-missed-only catch-up).
- Honor a **configurable lead time**: a task is created `lead_time_days` before its due date, with
  the occurrence date as its deadline (`end_date`).
- Honor a per-template **skip-if-previous-open** flag: do not generate the next instance while the
  last generated one is still incomplete.
- Link generated tasks back to their template (`TaskItem.template`, `SET_NULL`).
- Add a **`/api/template/`** owner-scoped DRF `ModelViewSet` (CRUD + a `run` action to generate now)
  with a serializer that surfaces a human-readable schedule summary and the next occurrence.
- Add **Angular UI**: a templates list, a create/edit form with a recurrence editor, a nav entry,
  and a "recurring" indicator on tasks generated from a template.
- Add **infrastructure**: `celery` + `redis` dependencies, a `organizer/celery.py` app, a beat
  schedule, `.env` keys, and supervisor programs (worker + beat) + Redis on prod. **BREAKING** for
  ops: production must run Redis and two new supervisor processes for scheduling to work (the API
  itself keeps working without them; only auto-generation is inert).

## Impact
- Affected specs:
  - **recurring-tasks** (new capability): templates, recurrence, generation semantics, engine, API.
  - **task-management** (ADDED): `TaskItem.template` linkage.
  - **web-frontend** (ADDED): template management UI + recurring indicator.
- Affected code:
  - `tasks/models.py` (new `TaskTemplate`, `TaskItem.template` FK) + migration.
  - `tasks/recurrence.py` (new: occurrence math + `materialize_due_tasks`).
  - `tasks/tasks.py` (new: Celery `@shared_task`), `organizer/celery.py`, `organizer/__init__.py`.
  - `tasks/management/commands/generate_recurring_tasks.py` (new).
  - `tasks/api/serializers.py`, `tasks/views.py`, `organizer/urls.py` (new viewset + route).
  - `organizer/settings.py`, `.env.example`, `pyproject.toml`/`uv.lock`, `requirements.txt`.
  - `frontend/src/app/templates/*` (new area) + nav + task badge; task serializer read-only field.
  - `docs/deployment.md` (Redis + worker/beat supervisor programs).
