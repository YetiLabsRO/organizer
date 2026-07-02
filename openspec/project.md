# Project Context

## Purpose
Organizer is a personal task & project organizer: users capture tasks (with status, priority,
dates, sub-tasks, tags, comments), group them into projects, and focus their day with a
"for today" flag. It exposes a REST API consumed by an Angular single-page app.

## Tech Stack
- **Backend**: Python 3.12+, Django 6, Django REST Framework, django-filter, django-model-utils.
- **Auth**: dj-rest-auth (DRF token login).
- **Database**: PostgreSQL (psycopg v3).
- **Frontend**: Angular (NgModule-based SPA) in `frontend/`, ng-bootstrap + Bootstrap + Angular Material.
- **Tooling**: uv (Python deps/lockfile), ruff (lint/format), openspec (spec-driven changes).

## Project Conventions

### Code Style
- Python: PEP 8, 120-col, double quotes, isort-ordered imports, f-strings. Enforced by ruff
  (config in `pyproject.toml`). Class-based views; `get_user_model()`; `__str__` + `Meta` on models.
  See `.junie/guidelines.md`.
- Angular: target signals, standalone components, `ChangeDetectionStrategy.OnPush`, and the new
  `@if`/`@for` control flow for new/changed code (legacy code is still NgModule-based). See
  `frontend/CLAUDE.md`.

### Architecture Patterns
- Single Django app `tasks` holds all domain models and the API. DRF `ModelViewSet`s under `/api/`,
  serializers in `tasks/api/serializers.py`, task filtering in `tasks/filters.py`.
- Default `auth.User` (no custom user model). All API endpoints require authentication.

### Testing Strategy
- Django test runner (`uv run python manage.py test`). Coverage is currently thin; new behavior
  should ship with tests.

### Git Workflow
- Default branch `develop`. Production has historically tracked a much older HEAD; the modernized
  code lives on `develop`.

## Domain Context
- A **TaskItem** has title, description, status (idea/blocked/inprogress/givenup), priority
  (high/normal/low), start/end (deadline) dates, an optional parent task, ordering, an owner,
  tags, an optional project, and a `for_today` flag. Saving a task inherits its project's tags.
- A **Project** groups tasks and carries its own tags. A **Tag** has a name, slug, color, and
  description. A **TaskComment** is authored by a user against a task.

## Important Constraints
- PostgreSQL only. Legacy production data lives in a 2017 `organize_*` schema and must be migrated
  into the current `tasks_*` schema (see `docs/data-migration.md`).

## External Dependencies
- None.
