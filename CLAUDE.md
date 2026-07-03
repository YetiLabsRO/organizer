<!-- OPENSPEC:START -->
# OpenSpec Instructions

These instructions are for AI assistants working in this project.

Always open `@/openspec/AGENTS.md` when the request:
- Mentions planning or proposals (words like proposal, spec, change, plan)
- Introduces new capabilities, breaking changes, architecture shifts, or big performance/security work
- Sounds ambiguous and you need the authoritative spec before coding

Use `@/openspec/AGENTS.md` to learn:
- How to create and apply change proposals
- Spec format and conventions
- Project structure and guidelines

Keep this managed block so 'openspec update' can refresh the instructions.

<!-- OPENSPEC:END -->

# CLAUDE.md

Guidance for Claude Code when working in this repository.

## What this is

**Organizer** — a personal task & project organizer. A Django REST API backend (repo root) plus an
Angular single-page app (`frontend/`). The two were previously separate repos; the Angular app was
consolidated in-tree from the now-deprecated `organizer-ui` repository.

## Architecture

- **Backend** — Django 6 + Django REST Framework, single app `tasks`. Project package is `organizer/`.
  - Models (`tasks/models.py`): `TaskItem`, `Project`, `Tag`, `TaskComment`. Default `auth.User`
    (no custom user model — `AUTH_USER_MODEL` is intentionally commented out).
  - API (`tasks/views.py`, router in `organizer/urls.py`): DRF `ModelViewSet`s under `/api/`:
    `/api/task/`, `/api/tag/`, `/api/project/`, `/api/comments/`. Serializers live in
    **`tasks/api/serializers.py`** (not `tasks/serializers.py`). Filtering for tasks is in
    `tasks/filters.py` (`TaskFilterSet`, incl. the `contains` OR-filter and `tags` by slug).
  - There is one server-rendered template view, `MainAppView` at `/` (`tasks/templates/tasks/`).
- **Frontend** — Angular SPA in `frontend/` (NgModule-based). Talks to the API via
  `Authorization: Token <key>` (DRF TokenAuthentication). See `frontend/CLAUDE.md`.

## Authentication

**DRF Token** — login via dj-rest-auth at `/rest-auth/login/`, configured in `organizer/settings.py`
`REST_FRAMEWORK`. The token payload is customized by `UserTokenSerializer`
(`tasks/api/serializers.py`) returning `{key, user, role}` (wired via
`REST_AUTH["TOKEN_SERIALIZER"]`). This is what the Angular app uses.

All API endpoints require authentication (`IsAuthenticated` default permission).

## Commands

Python is managed with **uv** (not pip directly). The lockfile `uv.lock` is the source of truth;
`requirements.txt` is generated from it for the production pip deploy.

```bash
uv sync                                   # install/refresh the .venv from uv.lock
uv run python manage.py runserver         # dev server on :8000
uv run python manage.py migrate           # apply migrations
uv run python manage.py makemigrations    # after model changes
uv run python manage.py test              # test suite
uv run ruff check .                       # lint  (config in pyproject.toml)
uv run ruff format .                      # format
uv export --format requirements-txt --no-hashes --no-dev -o requirements.txt   # refresh prod reqs

# Frontend (see frontend/CLAUDE.md)
cd frontend && npm install && npm start   # ng serve on :4200
```

Configuration is read from a `.env` file at the repo root via **python-decouple** (see
`.env.example` for the keys: `SECRET_KEY`, `DEBUG`, `ALLOWED_HOSTS`, `DB_*`, `CORS_ALLOWED_ORIGINS`).
Real OS environment variables take precedence over the file, so prod/CI inject them directly.
Postgres is the only supported database (`psycopg` v3).

## Worktrees

Use `bin/wt` to create and tear down git worktrees — never run `git worktree add/remove`
directly. The wrapper provisions a **per-worktree Postgres DB** (seeded from your main DB via
`pg_dump`), a uv-managed in-tree `.venv` (`uv sync` from `uv.lock`; deps hardlinked from uv's
shared cache, so each worktree adds almost no disk), a fresh `.env` (patched `DB_NAME` +
`DB_TEST_NAME`), a generated `.envrc` that activates `$PWD/.venv`, and copies
`.claude/settings.local.json` so the agent keeps its permissions. Requires `uv` and `pg_dump`
on PATH.

- `bin/wt new <branch> [path]` — create (branches off **fresh `origin/develop`**; path defaults to
  `.claude/worktrees/<slug>`). Override the base with `WT_BASE_BRANCH=<branch> bin/wt new …`.
- `bin/wt rm <path> [--force]` — drop the DB + worktree (the in-tree `.venv` goes with the dir).
- `bin/wt sync [path]` — rebase the worktree branch onto fresh `origin/develop` and check the
  migration graph is single-leaf. **Run right before finalizing a PR**, then regenerate migrations.
- `bin/wt prune [--force]` — drop `<main_db>_*` Postgres DBs orphaned by worktrees removed without
  `wt rm`; dry-run unless `--force` (refuses if any live worktree's DB name is unresolvable).
- `bin/wt template <refresh|check>` — maintain a shared `<main_db>_test_template` Postgres DB so
  cold test-DB builds clone (`CREATE DATABASE … WITH TEMPLATE …`) instead of replaying every
  migration. `refresh` drops + recreates + migrates it; `check` prints whether it exists.
  `settings.py` honours `TEST_DB_TEMPLATE` via Django's `TEST["TEMPLATE"]`, and `bin/wt new`
  auto-sets that env var in new worktrees whenever the template is present. Refresh after new
  migrations land on `develop`.
- `bin/wt ls` — list worktrees.

The slug is the branch name lowercased with non-alphanumerics → `_`; it names the DB
`<main_db>_<slug>` and the test DB `test_<main_db>_<slug>`. After `cd`-ing into a worktree,
`direnv` activates its in-tree `.venv` automatically. `python-decouple` is anchored to
`BASE_DIR/.env` (see `settings.py`), so each worktree reads its own `.env` regardless of cwd — no
per-worktree DB collisions. `bin/wt` provisions the **backend** only; to run the Angular SPA from a
worktree, `cd frontend && npm install` there, and pass explicit ports when running servers
(`manage.py runserver 0.0.0.0:8001`, `ng serve --port 4300`) to avoid clashing with other worktrees.

## Conventions

- **Python/Django**: follow `.junie/guidelines.md` (PEP 8, 120-col, double quotes, isort, CBVs,
  `get_user_model()`, `__str__` + `Meta` on models). Lint/format with ruff before committing.
- When adding deps, edit `pyproject.toml` then run `uv lock` (or `uv add <pkg>`); never hand-edit
  `requirements.txt` — regenerate it with `uv export`.
- **Frontend**: see `frontend/CLAUDE.md`.

## Planning & specs (openspec)

**openspec (`openspec/`) is the single source of truth for requirements, plans, and tasks.** The old
`docs/{requirements,plan,tasks}.md` (R#/P# checklist) system has been removed — do not recreate it.

- Specs under `openspec/specs/` describe current, shipping behavior (the baseline): `task-management`,
  `project-management`, `tag-management`, `task-comments`, `authentication`, `web-frontend`.
- For any non-trivial change, scaffold a change proposal under `openspec/changes/<id>/`
  (proposal + tasks + spec deltas) instead of editing a baseline spec directly.
- Read `openspec/AGENTS.md` for the full workflow; run `openspec list` and
  `openspec validate --strict` to check your work.

## Data migration

Production runs the legacy 2017 `organize_*` schema. `tasks/management/commands/migrate_legacy.py`
moves a production dump into the current `tasks_*` schema — see `docs/data-migration.md`.
