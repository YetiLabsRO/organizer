## Context
Organizer is a lean Django + DRF backend (single `tasks` app, Postgres) with an Angular SPA, deployed
to a single supervisor-managed server. There is currently **no async/scheduling infrastructure**.
The user wants tasks that repeat on a cadence ("1st of every month", "every N days/weeks/months") to
be created automatically. They chose Celery + Redis + beat for the trigger, structured recurrence
fields (RRULE-ready), latest-missed-only catch-up, and a configurable lead time.

## Goals / Non-Goals
- **Goals**
  - Define a recurring task once as a template; have the system generate real `TaskItem`s on schedule.
  - Idempotent, safe-to-re-run generation; no duplicate tasks for the same occurrence.
  - Latest-missed-only catch-up so downtime never produces a backlog pile.
  - Per-template "skip while the previous instance is still open".
  - Configurable lead time (create N days before the deadline).
  - A path to full RRULE later with no breaking schema change.
- **Non-Goals**
  - Full iCal RRULE evaluation in v1 (column reserved; generator branch is a stub).
  - Backfilling every missed occurrence (explicitly rejected — latest-only).
  - Sub-task templates / templated task trees (single task per occurrence in v1).
  - Notifications/reminders (a future, separate change that Celery also enables).

## Decisions

### Decision: One `TaskTemplate` model carrying both blueprint and recurrence
Keep v1 simple: a single table holds the task blueprint fields **and** the recurrence rule, rather
than splitting "template" from "schedule". Generated tasks copy the blueprint at creation time, so
later edits to a template do not retroactively change already-generated tasks.
- **Alternatives**: separate `Schedule` + `Template` tables (more flexible, more joins/UI for no
  current need); reusing an existing `TaskItem` flagged `is_template` (overloads the model, pollutes
  task lists/filters). Rejected for v1.

### Decision: Structured recurrence columns, `rrule` reserved
Columns: `frequency` (daily/weekly/monthly/yearly), `interval` (PositiveInt ≥ 1), `day_of_month`
(1–31, nullable), `weekdays` (Postgres `ArrayField` of 0–6 = Mon–Sun, nullable), `month_of_year`
(1–12, nullable, for yearly), `start_on` (date, default = creation date), `end_on` (date, nullable),
plus a nullable `rrule` text column. The occurrence generator computes dates from the structured
fields; if `rrule` is non-null it takes precedence (v1: raise/ignore until implemented). This lets a
future change add `python-dateutil`/`django-recurrence` without migrating existing rows.
- **Alternatives**: RRULE-only from day one (extra dep + heavier Angular editor for cases the user
  doesn't need yet). Rejected per the "structured now, RRULE-ready" choice.

### Decision: Pure core + Celery beat + management command
Occurrence math and materialization live in `tasks/recurrence.py` as plain functions
(`next_occurrence_on_or_after`, `due_occurrence(template, today)`, `materialize_due_tasks(template,
today)`), unit-testable with no broker. A Celery `@shared_task generate_recurring_tasks` iterates
active templates and calls the core; **celery beat** schedules it daily
(`CELERY_BEAT_SCHEDULE`, hour configurable via env). The same core is exposed as a
`generate_recurring_tasks` management command so it runs in CI (no Redis) and can be triggered
manually/from the API `run` action.
- **Alternatives**: cron + management command only (lighter, but the user chose Celery for the
  headroom it gives future async work); in-process APScheduler (misfires with multiple workers,
  needs a lock). Static `CELERY_BEAT_SCHEDULE` chosen over `django-celery-beat` to avoid an extra
  app + migrations; can be swapped later if the schedule needs editing from the admin.

### Decision: Idempotency & latest-missed-only via `last_generated_occurrence`
Each template stores `last_generated_occurrence` (date). For a run on date `T`:
1. An occurrence with due date `O` becomes **eligible** when `T >= O − lead_time_days`, and
   `start_on <= O <= end_on` (if set).
2. Among eligible occurrences with `O > last_generated_occurrence` (or all, if never generated),
   take the **greatest** `O` = `O*` (latest-missed-only; earlier gaps are skipped).
3. If none, do nothing.
4. If `skip_if_previous_open` and the template's most recent generated task is not `completed`, do
   nothing **and do not advance** `last_generated_occurrence` (retry next run once it's completed).
5. Otherwise create one `TaskItem` (copy blueprint, `end_date = O` at end of day, `template = self`,
   `owner = template.owner`, copy tags, status `idea`), then set `last_generated_occurrence = O*`.
Because step 2 keys off `last_generated_occurrence`, re-running the task the same day is a no-op.
- **Alternatives**: a `GeneratedOccurrence` ledger table (needed only for backfill, which is out of
  scope). Rejected as overkill for latest-only.

### Decision: `TaskItem.template` FK with `SET_NULL`
Generated tasks reference their template (`related_name="generated_tasks"`). Deleting a template
keeps its tasks and clears the link, mirroring the existing `project`/`parent_task` `SET_NULL`
pattern. The task serializer exposes `template` read-only so the SPA can badge recurring tasks.

## Risks / Trade-offs
- **New operational surface (Redis + 2 supervisor programs).** → The web API is unaffected if they
  are down; only auto-generation pauses. Document setup in `docs/deployment.md`; keep the management
  command as a manual fallback (`* * cron` or hand-run) if Redis is unavailable.
- **Timezone / DST around day boundaries.** → Do occurrence math in the project timezone on `date`
  objects; set `end_date` at local end-of-day. Cover month rollovers (e.g. day_of_month 31 in
  February → clamp to last valid day) with tests.
- **Lead time + skip-if-open interaction** could starve generation if a task is never completed. →
  Accepted: that is the intended "don't pile up" behavior; the template stays visible and pausable.
- **Celery task overlap** if a run is slow. → Generation is idempotent and cheap; use a single beat
  entry. Add a lock only if it proves necessary.

## Migration Plan
1. Ship model + migration (additive; nullable FK, no data backfill).
2. Deploy code; install `celery`/`redis` deps.
3. Provision Redis + supervisor `organizer-celery-worker` and `organizer-celery-beat` programs.
4. Until beat is live, run `manage.py generate_recurring_tasks` manually (or via system cron) — same
   result. Rollback = stop worker/beat; templates simply stop generating (no data loss).

## Open Questions
- Should the recurrence editor support "last day of month" / "Nth weekday" in v1, or wait for RRULE?
  (Proposed: wait — `day_of_month` clamps to month length; nth-weekday is an RRULE-era feature.)
- Should `run`-now bypass `skip_if_previous_open`? (Proposed: yes — an explicit manual action is an
  override.)
