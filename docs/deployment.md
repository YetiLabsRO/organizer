# Deployment (GitHub Actions)

Two workflows deploy to production on push to **`develop`** (the branch the production server
tracks). Both also run on `pull_request` (build/test only — no deploy) and can be triggered
manually via `workflow_dispatch`. They're modelled on the weinland / volunhub deploy pipelines.

- **[deploy-backend.yaml](../.github/workflows/deploy-backend.yaml)** — runs Django `check` +
  `migrate` + `test` against a throwaway Postgres service, then (on `develop`) SSHes to the server,
  backs up the production DB with `pg_dump`, `git reset --hard origin/develop`, installs deps into
  `.venv`, `collectstatic`, runs migrations **only if pending**, and restarts the service.
- **[deploy-frontend.yaml](../.github/workflows/deploy-frontend.yaml)** — `npm ci`, `npm test`
  (vitest), `npm run build`, then (on `develop`) tars `frontend/dist/organizer-frontend/browser`,
  scps it over, and unpacks it into the web root.

## Required GitHub configuration

Set these under **Settings → Secrets and variables → Actions** (and create a `production`
environment for the deploy jobs):

| Kind     | Name                 | Example / purpose                                   |
|----------|----------------------|-----------------------------------------------------|
| Variable | `SSH_USER`           | deploy user on the server (e.g. `yeti`)             |
| Variable | `SSH_HOST`           | server hostname/IP                                  |
| Variable | `SSH_PORT`           | SSH port (e.g. `22`)                                |
| Variable | `DEPLOY_PATH`        | backend checkout path, e.g. `/var/app/organizer`    |
| Variable | `RESTART_COMMAND`    | e.g. `sudo supervisorctl restart organizer` (defaults to `sudo systemctl restart organizer`) |
| Variable | `FRONTEND_WEB_ROOT`  | static web root, e.g. `/var/www/organizer`          |
| Secret   | `SSH_KEY`            | private key authorised on the server                |

## Server expectations

- Backend lives at `DEPLOY_PATH` as a git checkout with a `.venv/` and a `.env` (holding `DB_*`,
  `SECRET_KEY`, `ALLOWED_HOSTS`, …). The DB-backup step sources that `.env` to run `pg_dump`.
- The deploy user can run the configured restart command (and `sudo` for the frontend web-root copy).
- Database dumps are written to `/var/backups/organizer/` and pruned after 7 days.

## Recurring-task scheduling (Celery + Redis)

Recurring task templates are materialized into real tasks by a **Celery beat** schedule (see
`organizer/celery.py` and `CELERY_BEAT_SCHEDULE` in `organizer/settings.py`). This needs a **Redis**
broker and two long-running processes alongside the web app. The REST API keeps working without them
— only *automatic* generation pauses — so this is optional-but-recommended infrastructure.

Set the broker in the app's `.env` (see `.env.example`):

```
CELERY_BROKER_URL=redis://localhost:6379/0
RECURRING_TASKS_HOUR=6        # hour of day (local TIME_ZONE) the daily job runs
```

Run Redis (`sudo apt install redis-server`), then add two **supervisor** programs (the project already
uses supervisor for the web app):

```ini
[program:organizer-celery-worker]
command=/var/app/organizer/.venv/bin/celery -A organizer worker -l info
directory=/var/app/organizer
autostart=true
autorestart=true

[program:organizer-celery-beat]
command=/var/app/organizer/.venv/bin/celery -A organizer beat -l info
directory=/var/app/organizer
autostart=true
autorestart=true
```

`supervisorctl reread && supervisorctl update` to pick them up. After a deploy that changes task code,
restart them alongside the web app (`supervisorctl restart organizer organizer-celery-worker organizer-celery-beat`).

**Fallback without Celery/Redis:** the same generation logic is a management command, so a plain cron
entry works too:

```
0 6 * * *  cd /var/app/organizer && .venv/bin/python manage.py generate_recurring_tasks
```
