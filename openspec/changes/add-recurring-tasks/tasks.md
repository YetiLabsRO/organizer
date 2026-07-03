## 1. Data model
- [ ] 1.1 Add `TaskTemplate` to `tasks/models.py`: blueprint fields (title, description, priority,
      estimated_time, project FK, tags M2M, owner FK) + recurrence fields (frequency, interval,
      day_of_month, weekdays `ArrayField`, month_of_year, start_on, end_on, nullable `rrule`) +
      controls (`lead_time_days`, `skip_if_previous_open`, `is_active`, `last_generated_occurrence`)
      with `__str__` and `Meta`.
- [ ] 1.2 Add `TaskItem.template` FK (`on_delete=SET_NULL`, null/blank, `related_name="generated_tasks"`).
- [ ] 1.3 `makemigrations` and review the generated migration.

## 2. Recurrence core (framework-free, unit-tested)
- [ ] 2.1 Add `tasks/recurrence.py`: `next_occurrence_on_or_after(template, date)`,
      `due_occurrence(template, today)` (latest eligible occurrence honoring lead time, start/end,
      day-of-month clamping), and `materialize_due_tasks(template, today)` (idempotency via
      `last_generated_occurrence`, skip-if-previous-open, blueprint copy incl. tags, `end_date = O`).
- [ ] 2.2 Unit tests: daily/weekly/monthly/yearly cadence, interval > 1, day_of_month clamp
      (Jan 31 → Feb), lead time, start/end bounds, latest-missed-only, skip-if-open (block + resume),
      idempotent re-run, inactive templates.

## 3. Scheduling engine (Celery + Redis + beat)
- [ ] 3.1 Add `celery` + `redis` to `pyproject.toml`; `uv lock`; regenerate `requirements.txt`.
- [ ] 3.2 Add `organizer/celery.py` (Celery app) and load it in `organizer/__init__.py`.
- [ ] 3.3 Settings: `CELERY_BROKER_URL`/`CELERY_RESULT_BACKEND` from decouple; `CELERY_BEAT_SCHEDULE`
      with a daily entry at a configurable hour; add keys to `.env.example`.
- [ ] 3.4 Add `tasks/tasks.py` with a `generate_recurring_tasks` `@shared_task` iterating active
      templates and calling the core (in a per-template transaction).
- [ ] 3.5 Add `tasks/management/commands/generate_recurring_tasks.py` calling the same core (CI /
      manual / fallback path — no broker required).

## 4. API
- [ ] 4.1 Add `TaskTemplateSerializer` in `tasks/api/serializers.py`: recurrence fields, read-only
      schedule summary + `next_occurrence`, validation (interval ≥ 1, weekdays required for weekly,
      day_of_month range, end_on ≥ start_on).
- [ ] 4.2 Add owner-scoped `TaskTemplateViewSet` (CRUD; `get_queryset` filters by `request.user`;
      `perform_create` sets owner) with a `run` detail action that generates the due task now.
- [ ] 4.3 Register `router.register(r'template', TaskTemplateViewSet)` in `organizer/urls.py`.
- [ ] 4.4 Add read-only `template` field to `TaskSerializer`/`TaskListSerializer`.
- [ ] 4.5 API tests: owner scoping, CRUD, validation errors, `run` action, template field on tasks.

## 5. Frontend (Angular)
- [ ] 5.1 Add a `templates` feature area: service (`/api/template/`), list component (summary, next
      occurrence, active toggle, run-now/edit/delete), and form component with a frequency-adaptive
      recurrence editor, lead time, skip-if-open toggle; reuse `shared/project-picker` and
      `shared/tag-chips-input`.
- [ ] 5.2 Add a route + main-nav entry for templates.
- [ ] 5.3 Show a recurring indicator on task list/detail (from the task `template` field) linking to
      the template.
- [ ] 5.4 Frontend build passes (`npm run build`).

## 6. Ops & docs
- [ ] 6.1 Document Redis + `organizer-celery-worker` and `organizer-celery-beat` supervisor programs
      in `docs/deployment.md`; note the management-command fallback.
- [ ] 6.2 Confirm the CI test job (no Redis) covers the management command / core, not the broker.

## 7. Validation
- [ ] 7.1 `uv run ruff check .` and `uv run ruff format .` clean.
- [ ] 7.2 `uv run python manage.py test` green.
- [ ] 7.3 `openspec validate add-recurring-tasks --strict` passes.
