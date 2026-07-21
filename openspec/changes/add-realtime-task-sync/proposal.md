# Change: Real-time task sync over WebSockets

## Why

A task list open in one browser goes stale the moment the same account changes a task somewhere
else — another tab, the phone PWA, an MCP client, or the nightly recurring-task job. The only way to
see the truth today is a manual reload. Users expect an open list to reflect reality.

## What Changes

- Add a **WebSocket endpoint at `/ws/tasks/`** (Django Channels) that streams task-change events to
  every client of the authenticated user.
- **Authenticate the socket with a first message** (`{"type": "auth", "token": "<drf-token>"}`),
  because browsers cannot set an `Authorization` header on a WebSocket handshake. Unauthenticated
  sockets are closed with code `4401` after a short grace period. The token never enters a URL, so
  it stays out of access logs.
- **Broadcast `TaskItem` changes from model signals** (`post_save` / `post_delete`), fired on
  `transaction.on_commit`, to a per-owner group. Signals — rather than viewset hooks — are the single
  choke point that catches *every* write path: the REST API, the MCP server, Celery recurring-task
  generation, and the Django admin. The on-commit handler re-reads the row and serializes it, so tags
  a project inherits inside `save()` (and tags a serializer sets right after calling `save()`) are in
  the payload without a separate `m2m_changed` hook.
- Add a **Redis channel layer** (`channels_redis`). Production already runs Redis for Celery and
  serves uvicorn with `--workers 3`, so cross-process fan-out is mandatory — an in-memory layer
  would only reach clients that happened to land on the same worker.
- **Degrade gracefully:** if Redis is unreachable, the broadcast is logged and swallowed. A failing
  channel layer MUST NOT fail the write that triggered it — same philosophy as the existing
  optional-Celery design.
- Angular gains a root **`TaskEventsService`**: it connects when authenticated, reconnects with
  exponential backoff, heartbeats, and exposes an event stream. `TaskListComponent` and
  `PriorityFocusListComponent` subscribe and refresh in place.
- Events are ordered per task with the existing **`changed_date`** field, so a stale or out-of-order
  event is dropped rather than briefly rendering an older state over a newer one.

Out of scope: live updates for projects, tags, and comments (`Project` and `Tag` have no owner FK,
so per-user scoping would need an ownership model first). The mechanism is built to extend.

## Impact

- **Affected specs:** `realtime-sync` (new), `web-frontend`
- **Affected code:**
  - New: `tasks/apps.py`, `tasks/signals.py`, `tasks/realtime.py`, `tasks/consumers.py`,
    `tasks/routing.py`, `tasks/test_realtime.py`
  - Modified: `organizer/asgi.py` (route non-MCP `websocket` scopes), `organizer/settings.py`
    (`INSTALLED_APPS`, `CHANNEL_LAYERS`), `pyproject.toml` + `requirements.txt`
  - Frontend: new `task-events.service.ts`; modified `task-list.component.ts`,
    `priority-focus-list.component.ts`, `task-data-source.ts`, `environment*.ts`
- **Deployment (needs a server-side change — the app will not work over WS without it):**
  - nginx needs a **new `/ws/` location** with `Upgrade` / `Connection: upgrade` headers. The
    existing `/mcp` block sets `Connection ""`, which is the *opposite* of a WS upgrade — it must
    not be copied. Without a `/ws/` block the SPA catch-all `location /` swallows the request.
  - uvicorn needs WebSocket protocol support (`uvicorn[standard]`); the current bare `uvicorn`
    dependency cannot serve WebSockets.
