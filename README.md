organizer
=========

Personal task & project organizer — a Django REST API backend plus an Angular single-page app
(`frontend/`). It also exposes an **OAuth-protected MCP server** at `/mcp` so LLM clients (Claude
et al.) can manage your tasks, projects, tags, and comments as tools.

- Local development, architecture, and commands: see [CLAUDE.md](CLAUDE.md) and
  [frontend/CLAUDE.md](frontend/CLAUDE.md).
- CI/CD deployment: see [docs/deployment.md](docs/deployment.md).
- Server-side setup for the MCP / OAuth server: **below**.

Quick start (local):

```bash
uv sync
uv run python manage.py migrate
uv run uvicorn organizer.asgi:application    # serves REST API, admin, AND /mcp on :8000
```

---

## Server-side setup: MCP + OAuth 2.1

The `/mcp` endpoint is a remote **Model Context Protocol** server secured with OAuth 2.1
(authorization-code + PKCE), with this Django app acting as the authorization server via
`django-oauth-toolkit`. Setting it up in production is three things: **env vars**, **run under
ASGI**, and **serve it over HTTPS**.

This assumes the backend is already deployed as described in [docs/deployment.md](docs/deployment.md)
(a git checkout at `DEPLOY_PATH` with a `.venv/` and a `.env`, fronted by a reverse proxy, restarted
by a process manager). The GitHub Actions deploy already runs `pip install -r requirements.txt`
(which now includes `uvicorn`) and `manage.py migrate` (which creates the `oauth2_provider` tables),
so the steps below are the **one-time** server changes.

### 1. Environment (`.env`)

Add these keys (alongside the existing `SECRET_KEY`, `DEBUG=False`, `ALLOWED_HOSTS`, `DB_*`):

```ini
# Public, externally-reachable base URL — MUST be the HTTPS URL clients connect to.
# It anchors the OAuth issuer and the MCP resource identifier in discovery metadata.
MCP_BASE_URL=https://organizer.example.com

# OAuth token lifetimes in seconds (optional; defaults shown = 8h / 30d).
OAUTH_ACCESS_TOKEN_TTL=28800
OAUTH_REFRESH_TOKEN_TTL=2592000
```

Make sure the domain is in `ALLOWED_HOSTS`. **HTTPS is required** — Claude's remote connector (and
OAuth 2.1) will not use an `http://` public URL. `MCP_BASE_URL` must exactly match the URL clients
connect to (no trailing slash).

### 2. Run under ASGI (uvicorn)

`/mcp` uses async streaming, so the app must run under **ASGI**, not WSGI. Point your existing
service (whatever `RESTART_COMMAND` restarts — gunicorn/uwsgi today) at `uvicorn` running the ASGI
app. The REST API and admin continue to work under ASGI.

**systemd** (`/etc/systemd/system/organizer.service`):

```ini
[Unit]
Description=Organizer (Django ASGI + MCP)
After=network.target

[Service]
User=yeti
WorkingDirectory=/var/app/organizer
EnvironmentFile=/var/app/organizer/.env
ExecStart=/var/app/organizer/.venv/bin/uvicorn organizer.asgi:application \
    --host 127.0.0.1 --port 8000 --workers 3 \
    --proxy-headers --forwarded-allow-ips='*'
Restart=on-failure

[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now organizer
```

**supervisor** equivalent (`/etc/supervisor/conf.d/organizer.conf`) — this matches the default
`RESTART_COMMAND` (`sudo supervisorctl restart organizer`):

```ini
[program:organizer]
command=/var/app/organizer/.venv/bin/uvicorn organizer.asgi:application
    --host 127.0.0.1 --port 8000 --workers 3 --proxy-headers --forwarded-allow-ips=*
directory=/var/app/organizer
user=yeti
autostart=true
autorestart=true
startsecs=5
startretries=3
; uvicorn with --workers spawns child processes — signal the whole group on stop/restart.
stopasgroup=true
killasgroup=true
stopsignal=INT
stdout_logfile=/var/log/organizer/uvicorn.log
stderr_logfile=/var/log/organizer/uvicorn.err.log
environment=PYTHONUNBUFFERED="1"
```

```bash
sudo mkdir -p /var/log/organizer && sudo chown yeti /var/log/organizer
sudo supervisorctl reread && sudo supervisorctl update
sudo supervisorctl start organizer
```

Notes:

- `stopasgroup`/`killasgroup` are important with `--workers` > 1 so supervisor stops the worker
  child processes too; `stopsignal=INT` triggers uvicorn's graceful shutdown.
- `--workers 3` is a starting point — tune to your CPU (a common rule is `2 × cores + 1`). The MCP
  transport is stateless, so multiple workers are safe with no shared session state.
- `--proxy-headers --forwarded-allow-ips=*` makes uvicorn honour `X-Forwarded-Proto`/`-For` from the
  proxy. `DB_*`, `SECRET_KEY`, `MCP_BASE_URL`, etc. are read from `.env` by python-decouple (anchored
  to the project dir), so supervisor doesn't need to inject them.

### 3. Reverse proxy (HTTPS + streaming)

Terminate TLS at your proxy and forward to uvicorn. The **only special rule** is for `/mcp`: disable
response buffering and allow long-lived connections so the MCP SSE stream flows.

**nginx** (nginx serves the Angular bundle and proxies the backend paths to uvicorn — the
`8000` below is a placeholder for whatever port your backend service listens on):

```nginx
server {
    listen 443 ssl;
    server_name organizer.example.com;
    # ssl_certificate ...; ssl_certificate_key ...;   # e.g. managed by Certbot

    root /var/www/organizer;          # Angular bundle
    index index.html;

    # Django backend (uvicorn/ASGI)
    location /api/       { proxy_pass http://127.0.0.1:8000; proxy_set_header Host $host; proxy_set_header X-Forwarded-Proto $scheme; }
    location /rest-auth/ { proxy_pass http://127.0.0.1:8000; proxy_set_header Host $host; proxy_set_header X-Forwarded-Proto $scheme; }
    location /admin/     { proxy_pass http://127.0.0.1:8000; proxy_set_header Host $host; proxy_set_header X-Forwarded-Proto $scheme; }

    # OAuth 2.1 server + discovery metadata (needed because `location /` below serves the SPA,
    # not a backend catch-all). Specific well-known prefixes do NOT shadow Certbot's acme-challenge.
    location /o/ { proxy_pass http://127.0.0.1:8000; proxy_set_header Host $host; proxy_set_header X-Forwarded-Proto $scheme; }
    location /.well-known/oauth-authorization-server { proxy_pass http://127.0.0.1:8000; proxy_set_header Host $host; proxy_set_header X-Forwarded-Proto $scheme; }
    location /.well-known/oauth-protected-resource   { proxy_pass http://127.0.0.1:8000; proxy_set_header Host $host; proxy_set_header X-Forwarded-Proto $scheme; }

    # MCP endpoint — must stream (SSE): no buffering, long read timeout, HTTP/1.1 keep-alive.
    location /mcp {
        proxy_pass http://127.0.0.1:8000;
        proxy_http_version 1.1;
        proxy_set_header Host              $host;
        proxy_set_header X-Forwarded-For   $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_set_header Connection        "";
        proxy_buffering    off;
        proxy_read_timeout 3600s;
    }

    location /static/ { alias /var/app/organizer/static/; }   # from collectstatic (STATIC_ROOT)
    location /        { try_files $uri $uri/ /index.html; }   # SPA client-side routing
}
```

(If instead your nginx has no SPA and `location /` is a plain `proxy_pass` to the backend, you only
need to add the streaming `location /mcp` block — the OAuth and well-known paths are already covered
by that catch-all.)

### 4. A Django user for consent

The OAuth authorize/consent screen requires a logged-in Django user (it redirects to the admin
login). Create one if you don't have it — this is also the account whose tasks the MCP tools manage:

```bash
/var/app/organizer/.venv/bin/python manage.py createsuperuser
```

### 5. Connect a client (e.g. Claude)

In Claude, add a **custom connector** with the URL `https://organizer.example.com/mcp`. Claude will:
discover the authorization server, **dynamically register itself** (RFC 7591), then open a browser
for you to log in and grant the `read`/`write` scopes. After approval the 18 task/project/tag/comment
tools are available. Access is revocable per user via the toolkit's authorized-tokens views.

> Discovery/OAuth happens server-to-server, so no CORS config is needed for Claude. Only add an
> origin to `CORS_ALLOWED_ORIGINS` if you use a **browser-based** MCP client.

### 6. Verify

```bash
# Authorization-server metadata (RFC 8414)
curl -s https://organizer.example.com/.well-known/oauth-authorization-server | python3 -m json.tool

# Protected-resource metadata (RFC 9728)
curl -s https://organizer.example.com/.well-known/oauth-protected-resource/mcp | python3 -m json.tool

# Unauthenticated /mcp must be challenged
curl -si -X POST https://organizer.example.com/mcp \
  -H 'Accept: application/json, text/event-stream' \
  -H 'Content-Type: application/json' \
  -d '{"jsonrpc":"2.0","id":1,"method":"tools/list"}' | grep -iE 'HTTP/|www-authenticate'
# => HTTP/1.1 401 Unauthorized
# => www-authenticate: Bearer ... resource_metadata="https://organizer.example.com/.well-known/oauth-protected-resource/mcp"
```

The `issuer` in the first response and the `resource`/`authorization_servers` in the second must
match `MCP_BASE_URL`. If they show `localhost`, `MCP_BASE_URL` isn't set in the server's environment.
