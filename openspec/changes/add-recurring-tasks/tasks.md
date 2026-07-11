## 1. Data model
- [x] 1.1 Add `TaskTemplate` to `tasks/models.py`: blueprint fields (title, description, priority,
      estimated_time, project FK, tags M2M, owner FK) + recurrence fields (frequency, interval,
      day_of_month, weekdays `ArrayField`, month_of_year, start_on, end_on, nullable `rrule`) +
      controls (`lead_time_days`, `skip_if_previous_open`, `is_active`, `last_generated_occurrence`)
      with `__str__` and `Meta`.
- [x] 1.2 Add `TaskItem.template` FK (`on_delete=SET_NULL`, null/blank, `related_name="generated_tasks"`).
- [x] 1.3 `makemigrations` and review the generated migration (`0009_tasktemplate_taskitem_template`).

## 2. Recurrence core (framework-free, unit-tested)
- [x] 2.1 Add `tasks/recurrence.py`: occurrence primitives (`first_occurrence`, `step`,
      `latest_occurrence_on_or_before`, `occurrence_on_or_after`, `next_occurrence`) honoring lead
      time, start/end, day-of-month clamping, plus `materialize_due_tasks(template, today)`
      (idempotency via `last_generated_occurrence`, skip-if-previous-open, blueprint copy incl. tags,
      `end_date = O`) and `schedule_summary`.
- [x] 2.2 Unit tests (`tasks/test_recurrence.py`): daily/weekly/monthly/yearly cadence, interval > 1,
      day_of_month clamp (Jan 31 → Feb), lead time, start/end bounds, latest-missed-only,
      skip-if-open (block + resume), idempotent re-run, inactive templates.

## 3. Scheduling engine (Celery + Redis + beat)
- [x] 3.1 Add `celery` + `redis` to `pyproject.toml`; `uv lock`; regenerate `requirements.txt`.
- [x] 3.2 Add `organizer/celery.py` (Celery app) and load it in `organizer/__init__.py`.
- [x] 3.3 Settings: `CELERY_BROKER_URL`/`CELERY_RESULT_BACKEND` from decouple; `CELERY_BEAT_SCHEDULE`
      with a daily entry at a configurable hour (`RECURRING_TASKS_HOUR`); add keys to `.env.example`.
- [x] 3.4 Add `tasks/tasks.py` with a `generate_recurring_tasks` `@shared_task` iterating active
      templates and calling the core (per-template transaction, one bad template can't abort the run).
- [x] 3.5 Add `tasks/management/commands/generate_recurring_tasks.py` calling the same core (CI /
      manual / fallback path — no broker required; supports `--date`).

## 4. API
- [x] 4.1 Add `TaskTemplateSerializer` in `tasks/api/serializers.py`: recurrence fields, read-only
      schedule summary + `next_occurrence`, validation (interval ≥ 1, day_of_month/month_of_year/
      weekday ranges, end_on ≥ start_on).
- [x] 4.2 Add owner-scoped `TaskTemplateViewSet` (CRUD; `get_queryset` filters by `request.user`;
      `perform_create` sets owner) with a `run` detail action that generates the due task now.
- [x] 4.3 Register `router.register(r'template', TaskTemplateViewSet)` in `organizer/urls.py`.
- [x] 4.4 Add read-only `template` field to `TaskSerializer`/`TaskListSerializer`. (Landed via the
      `enrich-task-ui` change, which also adds a read-only `template_title` for the UI badge.)
- [x] 4.5 API tests (`tasks/test_templates_api.py`): owner scoping, CRUD, validation errors, `run`
      action, template field on tasks, management command.

## 5. Frontend (Angular)
- [x] 5.1 Add a `templates` feature area: service (`/api/template/`), list component (summary, next
      occurrence, active toggle, run-now/edit/delete), and form component with a frequency-adaptive
      recurrence editor, lead time, skip-if-open toggle; reuses the ngx-chips tag input. (Project
      selection uses a native `<select>` rather than `shared/project-picker` — see PR notes.)
- [x] 5.2 Add routes + a "Recurring" main-nav entry for templates.
- [x] 5.3 Show a recurring indicator on task-list rows linking to the originating template. (The
      indicator markup landed in `enrich-task-ui`; this branch repoints it at `/templates/:id/edit`
      now that the route exists.)
- [x] 5.4 Frontend production build passes (`npm run build`).

## 6. Ops & docs
- [x] 6.1 Document Redis + `organizer-celery-worker` and `organizer-celery-beat` supervisor programs
      in `docs/deployment.md`; note the management-command/cron fallback.
- [x] 6.2 CI test job (no Redis) covers the management command + recurrence core, not the broker.

## 7. Validation
- [x] 7.1 `uv run ruff check .` clean. (Did not run `ruff format` — the baseline isn't ruff-formatted,
      so a repo-wide reformat would swamp the diff; new code was hand-formatted to match.)
- [x] 7.2 `uv run python manage.py test` green (49 tests).
- [x] 7.3 `openspec validate add-recurring-tasks --strict` passes.
