## Context

The backend is a Django 6 + DRF app already served under ASGI (`uvicorn organizer.asgi:application`,
`--workers 3`) because the MCP endpoint requires it. `organizer/asgi.py` is a hand-written composed
ASGI app, not a Channels `ProtocolTypeRouter`: it routes `/mcp` + the protected-resource metadata to
the MCP Streamable-HTTP app and everything else to Django, and it deliberately lets **the MCP app own
the `lifespan` scope** (Django's ASGI handler does not implement it).

Redis is already deployed (Celery broker for recurring-task generation). The Angular SPA is
standalone/signals-based, holds no shared task store, and authenticates with a long-lived DRF token
in `localStorage`.

## Goals / Non-Goals

**Goals**
- A task list open anywhere reflects a change made anywhere else for the same user, within ~1s.
- One broadcast path that covers all four writers: REST API, MCP server, Celery, admin.
- Redis being down degrades to today's behavior; it never fails a write.

**Non-Goals**
- Real-time for `Project` / `Tag` / `TaskComment` (no owner FK on the first two).
- Collaboration/multi-user sharing. Groups are strictly per-owner.
- Offline replay or an event log. A client that misses events reconnects and refetches.

## Decisions

### Django Channels rather than a hand-rolled ASGI socket

Channels is ~2 dependencies (`channels`, `channels_redis`) and gives us the group/fan-out primitive,
a tested consumer base class, and `WebsocketCommunicator` for tests. A hand-rolled socket over
`redis.asyncio` pub/sub would avoid the dependency but means owning heartbeats, backpressure, and
Redis reconnection ourselves. Not worth it.

**We do NOT set `ASGI_APPLICATION` to a `ProtocolTypeRouter`.** Doing so would hand `lifespan` to
Channels and break the MCP session manager, which currently owns it. Instead we add a *third branch*
to the existing `application()`, delegating only non-MCP `websocket` scopes to a bare
`URLRouter`:

```python
if scope["type"] == "websocket" and scope.get("path", "").startswith("/ws/"):
    await websocket_application(scope, receive, send)
    return
```

No `AuthMiddlewareStack` — we authenticate in-band (below), so no session/cookie middleware is
needed on the socket.

### First-message auth, not a query-string token

DRF tokens do not expire. Putting one in the WS URL writes a permanent credential into nginx access
logs and any intermediary. Instead:

1. Server `accept()`s the socket immediately but marks it unauthenticated, and arms a **5s deadline**.
2. Client's first frame is `{"type": "auth", "token": "<key>"}`.
3. Server resolves the token to a user, joins group `tasks.user.<pk>`, replies `{"type":"auth.ok"}`.
4. Bad or missing token → close with **4401**. The client treats 4401 as fatal (no reconnect storm)
   and only retries after a fresh login.

Any frame received before auth, other than the auth frame, is ignored.

### Broadcast from model signals, on commit

`post_save` / `post_delete` on `TaskItem`. Two subtleties drive the `transaction.on_commit` + re-read
design:

- `TaskItem.save()` attaches the project's tags **after** `super().save()`, so a payload serialized
  inside `post_save` would be missing tags.
- Broadcasting mid-transaction can publish a change that then rolls back.

So the receiver defers to `on_commit`, then **re-reads the row** and serializes it with
`TaskListSerializer` — the exact shape the list endpoint already returns, so the client can drop it
straight into its list. Deletes are the exception: the row is gone at commit time, so `owner_id` and
`id` are captured in the signal and only `{id}` is sent.

**No `m2m_changed` hook.** Every supported way to change a task's tags runs through `TaskItem.save()`
first — DRF's serializer calls `instance.save()` before assigning the m2m, and the model inherits
project tags inside `save()` — so `post_save` fires and `changed_date` (an `auto_now` field) is
bumped. The on-commit re-read then captures the final tags regardless of assignment order. A bare tag
mutation that skipped `save()` would leave `changed_date` untouched, so the client's stale-event guard
(below) would drop the event anyway; hooking `m2m_changed` would only emit redundant events that the
guard discards.

`owner` is nullable on `TaskItem` — an ownerless task has no group to broadcast to and is skipped.

The `group_send` bridge (`tasks/realtime.py`) wraps the whole broadcast — layer lookup included — in
a try/except that logs and swallows, so a dead Redis can never turn a task write into a 500.

### Redis failure is non-fatal

`group_send` is wrapped; on any exception it logs at `warning` and returns. A dead Redis must not
turn a task edit into a 500. This mirrors the existing "the REST API does not require Celery" stance.

### Ordering guard via `changed_date`

Clients keep the last-seen `changed_date` per task id and **drop any event whose `changed_date` is
not newer**. This solves three problems at once with no server-side plumbing:

- Out-of-order delivery across workers.
- Echo of the client's *own* write (its optimistic in-place mutation left `changed_date` stale, so
  the echo is genuinely newer and correctly applied — server truth wins).
- Rapid double-toggles briefly rendering the older of two in-flight states.

### Client refresh strategy

| Event | `TaskListComponent` (virtual scroll) | `PriorityFocusListComponent` (flat array) |
|---|---|---|
| `task.updated` | `dataSource.replace(task)` if it still matches the active filters, else `removeById` | patch in place, or drop if filtered out |
| `task.created` | debounced (300ms) refetch | debounced refetch |
| `task.deleted` | `removeById(id)` | filter out by id |

Creates refetch rather than splice because insert position depends on the active ordering and
filters, and `TaskDataSource` is a sparse windowed array with a server-provided `count` — the server
is the cheaper source of truth. A side-effect worth noting: this fixes the existing bug where a task
created from the app-wide drawer never appears in `TaskListComponent` (it subscribes to neither
`created$` nor anything else).

## Risks / Trade-offs

- **nginx must be reconfigured.** Until a `/ws/` location with upgrade headers is added, the SPA
  catch-all swallows the handshake and the socket silently never connects. → Client falls back to its
  current behavior (no live updates); ship the nginx snippet in the same PR's docs.
- **uvicorn without `[standard]` cannot speak WebSocket.** → Move the dependency to
  `uvicorn[standard]`; verify in CI's `check` step.
- **CI has no Redis service container** (Postgres only). → Tests override `CHANNEL_LAYERS` to
  `InMemoryChannelLayer`; the Redis layer is exercised manually/in prod, not in CI.
- Long-lived DRF tokens still authenticate the socket. First-message auth keeps them out of logs but
  does not make them expiring. Token rotation stays a separate concern.

## Migration Plan

No schema changes; no migrations. Deploy order: (1) merge backend + frontend, (2) add the nginx
`/ws/` block and reload, (3) restart the app under supervisor. Rolling back is just reverting — a
client whose socket won't connect behaves exactly as it does today.

## Open Questions

None blocking.
