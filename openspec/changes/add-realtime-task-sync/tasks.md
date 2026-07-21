## 1. Backend — dependencies and settings

- [x] 1.1 `uv add channels channels-redis` and change the `uvicorn` dependency to `uvicorn[standard]`
      (the bare package cannot serve WebSockets); then `uv export` to regenerate `requirements.txt`.
      `daphne` added as a **dev-only** dep so `channels.testing` imports under CI's `uv sync`
      (prod `requirements.txt`, exported `--no-dev`, stays uvicorn-only).
- [x] 1.2 Add `channels` to `INSTALLED_APPS` and a `CHANNEL_LAYERS` block backed by `channels_redis`,
      reading `CHANNELS_REDIS_URL` (default `redis://localhost:6379/1` — a different DB index than
      the Celery broker on `/0`). `ASGI_APPLICATION` left pointing at the existing composed app.
- [x] 1.3 Document `CHANNELS_REDIS_URL` in `.env.example`

## 2. Backend — signals

- [x] 2.1 Add `tasks/apps.py` with `TasksConfig.ready()` importing the signal module, and switch
      `INSTALLED_APPS` from `'tasks'` to `'tasks.apps.TasksConfig'` (did not set `default_auto_field`
      — `DEFAULT_AUTO_FIELD` is already set globally)
- [x] 2.2 Add `tasks/signals.py` (+ `tasks/realtime.py` for the group-send helper): `post_save` /
      `post_delete` on `TaskItem`, deferred to `transaction.on_commit`, re-reading the row and
      serializing with `TaskListSerializer` so project-inherited tags are included. Deletes capture
      `id` + `owner_id` and send only `{id}`. **No `m2m_changed` hook** — every tag change runs
      through `save()` first (bumping `changed_date` and firing `post_save`), so it is redundant and
      a bare m2m event would be dropped by the client stale-guard anyway (see design.md).
- [x] 2.3 Skip tasks with a null `owner` (the FK is nullable — there is no group to send to)
- [x] 2.4 Wrap the whole `group_send` (layer lookup included) so a channel-layer failure logs a
      warning and returns; a dead Redis MUST NOT turn a task write into a 500

## 3. Backend — consumer and routing

- [x] 3.1 Add `tasks/consumers.py`: `TaskEventsConsumer(AsyncJsonWebsocketConsumer)` — accepts
      immediately as unauthenticated, arms a 5s auth deadline, handles `{"type":"auth","token":...}`,
      resolves the DRF token, `group_add("tasks.user.<pk>")`, replies `{"type":"auth.ok"}`. Closes
      `4401` on bad/missing token or deadline. Ignores other frames before auth. Answers `ping`.
- [x] 3.2 Add `tasks/routing.py` mapping `ws/tasks/` to the consumer (a bare `URLRouter`)
- [x] 3.3 Add a `websocket` branch to `organizer/asgi.py` for paths under `/ws/`, delegating to the
      `URLRouter` (not a `ProtocolTypeRouter` — the MCP app keeps `lifespan`). `/mcp` branch stays
      ahead of it.

## 4. Backend — tests

- [x] 4.1 Add `tasks/test_realtime.py` using `WebsocketCommunicator` with
      `@override_settings(CHANNEL_LAYERS=…InMemoryChannelLayer)` — CI has no Redis service container
- [x] 4.2 Cover: valid token → `auth.ok`; invalid token → close `4401`; no auth frame → close `4401`;
      no events delivered before auth
- [x] 4.3 Cover: saving a task broadcasts `task.updated` to its owner and **not** to another user
- [x] 4.4 Cover: the payload includes project-inherited tags (guards the `save()` ordering trap)
- [x] 4.5 Cover: a task write still succeeds when the channel layer raises
- [x] 4.6 `/ws/tasks/` routes to the consumer through the real `organizer.asgi.application` (exercised
      by every consumer test); ping→pong keepalive covered

## 5. Frontend — event service

- [x] 5.1 Add `wsBase` to `environment.ts` (`ws://127.0.0.1:8000`) and `environment.prod.ts` (empty —
      derived from `location`)
- [x] 5.2 Add `task-events.service.ts` (root-provided): connects when `AuthService.loggedIn`, sends
      the auth frame on open, exponential backoff with jitter (1s → 30s cap), heartbeat, `connected`
      signal, `events$` stream. Treats close `4401` as fatal. Injected in `AppComponent` so it starts
      at app load.
- [x] 5.3 Drop events whose `changed_date` is not newer than the state already held for that task id

## 6. Frontend — wire the views

- [x] 6.1 Add a `refresh()` reconcile path to `task-data-source.ts` (re-fetches the window + resizes
      to the fresh total without blanking, so out-of-window inserts/removals converge)
- [x] 6.2 `TaskListComponent`: `task.updated` → `replace()` + debounced reconcile; `task.created` →
      debounced (300ms) `refresh()`; `task.deleted` → `removeById()` and decrement the count
- [x] 6.3 `PriorityFocusListComponent`: patch in place on update, debounced quiet `load(false)` on
      create, filter out on delete; counts re-read each event
- [x] 6.4 Refresh the open view on reconnect (`reconnected` event) to pick up what was missed
- [x] 6.5 Frontend tests (vitest) for the service: auth frame on open, backoff, `4401` fatal,
      logout teardown, reconnect event, stale-event drop (8 tests)

## 7. Deployment and docs

- [x] 7.1 Add an nginx `/ws/` location to `README.md` with `Upgrade` / `Connection "upgrade"` and a
      long `proxy_read_timeout`, with an explicit note that it is the opposite of the `/mcp` block
- [x] 7.2 Note in `docs/deployment.md` that Redis is now also the channel layer and the app must run
      under ASGI (`uvicorn[standard]`, `--workers 3` → Redis layer, not in-memory)
- [x] 7.3 Update `CLAUDE.md` + `frontend/CLAUDE.md` with the `/ws/tasks/` endpoint and the event flow

## 8. Verify

- [x] 8.1 `uv run ruff check .` passes; `uv run python manage.py test` — **120 tests pass** (16 new).
      (Repo-wide `ruff format` is not enforced — pre-existing files aren't format-clean — so only the
      new/edited lines were kept format-consistent with their neighbours.)
- [x] 8.2 `npm test` — **100 tests pass** (8 new); `npm run build` succeeds
- [ ] 8.3 Manual end-to-end drive under `uvicorn` + Redis (two browsers; and an MCP tool call) —
      **left for the reviewer/deploy**: needs a real Redis + browsers, out of reach of CI (no Redis
      service) and this automated run. The consumer/signal test suite exercises the same code paths.
