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
  `SECRET_KEY`, `ALLOWED_HOSTS`, `MCP_BASE_URL`, …). The DB-backup step sources that `.env` to run
  `pg_dump`.
- The service the restart command controls runs the app under **ASGI** (`uvicorn
  organizer.asgi:application`) — required so the `/mcp` MCP endpoint works; the REST API and admin
  run fine under ASGI too. See [Server-side setup: MCP + OAuth 2.1](../README.md#server-side-setup-mcp--oauth-21)
  for the systemd/supervisor unit, the HTTPS reverse-proxy rules (stream `/mcp`), and the required
  `MCP_BASE_URL`. `oauth2_provider` tables are created by the deploy's `migrate` step.
- The deploy user can run the configured restart command (and `sudo` for the frontend web-root copy).
- Database dumps are written to `/var/backups/organizer/` and pruned after 7 days.
