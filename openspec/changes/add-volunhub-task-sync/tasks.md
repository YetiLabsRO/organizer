# Tasks: Two-way VolunHub task sync

## 1. Scaffold & config
- [x] 1.1 Create the `integrations/volunhub/` app (`AppConfig`, label `volunhub`) and add it to
      `INSTALLED_APPS`
- [x] 1.2 Settings and `.env.example`:
      - `VOLUNHUB_BASE_URL`: https enforced unless `DEBUG`;
      - `VOLUNHUB_REDIRECT_URI`;
      - `VOLUNHUB_CLIENT_ID`: optional;
      - `VOLUNHUB_SYNC_MINUTES`: default 10;
      - the `CELERY_BEAT_SCHEDULE["sync-volunhub"]` entry.

      Token encryption reuses `INTEGRATIONS_TOKEN_KEY` (no new dependencies).
- [x] 1.3 `exceptions.py`: `VolunHubError`, `VolunHubNotConfigured`, `VolunHubAuthError`,
      `VolunHubAPIError(status_code, body)`, `VolunHubRateLimited(retry_after)`

## 2. Models & migration (design D3)
- [x] 2.1 `VolunHubOAuthClient`, unique `(base_url, redirect_uri)`; `VolunHubOAuthFlow` with
      `consume()` / `purge_expired()` and a 10-minute TTL
- [x] 2.2 `VolunHubConnection`:
      - encrypted token properties via `integrations/crypto.py`;
      - `granted_scope`, `status`, `content_push_enabled`;
      - derived `can_write` / `pushes_content`;
      - `mark_needs_reauth()`.
- [x] 2.3 `VolunHubProjectLink`: global, unique `external_id`, `auto_created`
- [x] 2.4 `VolunHubTaskLink`:
      - per user, unique `(user, external_id)`;
      - `task` OneToOne with `SET_NULL` (tombstone);
      - `state` / `removed_reason` / `removed_at`, `snapshot` JSON, `external_project_id`,
        `last_error`.
- [x] 2.5 `makemigrations` + `migrate`

## 3. OAuth (`oauth.py`, design D1/D2/D8)
- [x] 3.1 Metadata discovery from `/.well-known/oauth-authorization-server`
- [x] 3.2 Lazy DCR under a row lock. Fail closed unless the returned scope set is exactly
      `{mcp:tasks:read, mcp:tasks:write}`. Honour the `VOLUNHUB_CLIENT_ID` override.
- [x] 3.3 PKCE (verifier + S256 challenge) and authorize-URL builder
- [x] 3.4 Code exchange: public client, `client_id` + `code_verifier`, no secret. Apply the token
      response: expiry from `expires_in`, granted scope, and rejection when read scope is missing.
- [x] 3.5 Serialized refresh: `select_for_update`, re-read after taking the lock, persist the rotated
      refresh token, `invalid_grant` → `needs_reauth`
- [x] 3.6 Best-effort `/revoke`, sending `client_id`

## 4. API client (`client.py`, design D8)
- [x] 4.1 `httpx` client with Bearer auth and the path allow-list (tasks + projects prefixes; raise
      before sending otherwise)
- [x] 4.2 Proactive refresh near expiry, reactive refresh on `401` (retry once), backoff on
      `429`/`5xx` honouring `Retry-After`
- [x] 4.3 `list_assigned_tasks()`: `?mine=true&ordering=id`, follows `next`, all-or-nothing.
      `get_task(id)` returns the task or None on 404. `patch_task(id, fields)`.
      `set_state(id, state)`.

## 5. Mapping (`mapping.py`, design D4)
- [x] 5.1 Remote task → Organizer-representation dict:
      - `state_name` label → slug → (status, completed); ignore `completed`;
      - priority 1/2/3 → 1/2/4;
      - `deadline` → `end_date`;
      - UTC datetime normalization; description normalization.
- [x] 5.2 Organizer-representation field → VolunHub payload (content `PATCH` body; status target,
      with `givenup` → none)
- [x] 5.3 Status route planner: go through `planned` when the target isn't directly reachable

## 6. Sync engine (`sync.py`, design D5/D6/D7)
- [x] 6.1 Per-connection advisory lock; full listing; abort the run on a partial listing
- [x] 6.2 Import unlinked tasks: create task + link in one transaction, resolve the project
- [x] 6.3 Three-way merge per field:
      - apply local changes with one `save()`;
      - push changed content (`PATCH`), then status (route);
      - rebuild the snapshot from the responses;
      - per-link `last_error`, with failed fields left at `base`.
- [x] 6.4 Conflict rule: Organizer wins for pushable fields; VolunHub wins for fields that can't be
      pushed; `givenup` is kept
- [x] 6.5 `403` on `PATCH` → `content_push_enabled=False`, keep status push
- [x] 6.6 Removal probe (404 → deleted, 200 → unassigned, else untouched); re-attach on reappearance;
      delete tombstone links that are absent from the listing
- [x] 6.7 Projects: auto-create, rename while `auto_created`, never re-create a project that was
      deleted locally; project is import-only
- [x] 6.8 Run report and logging (created / updated / pushed / conflicts / removed / reattached /
      errors)

## 7. Notion exclusion (design D9)
- [x] 7.1 `integrations/notion/sync.py` `_push`: add `volunhub_link__isnull=True` to the
      unlinked-task query, with a soft guard so Notion still works if the VolunHub app is absent
- [x] 7.2 Notion test: VolunHub-linked tasks (active and removed) get no page

## 8. Endpoints & triggers (`views.py`, `urls.py`, `tasks.py`)
- [x] 8.1 DRF under `/api/integrations/volunhub/`:
      - `status/` (never returns tokens);
      - `connect/`;
      - `disconnect/` (revoke, delete the connection, mark links `disconnected`);
      - `sync/` (queues `sync_one`; `{retry_content: true}` re-enables content push);
      - `projects/` (list, scoped to the caller's links);
      - `projects/<external_id>/merge/`.
- [x] 8.2 Browser callback `/integrations/volunhub/callback/`, redirecting to
      `/settings/integrations?volunhub=…`
- [x] 8.3 Wire `api_urlpatterns` / `browser_urlpatterns` in `organizer/urls.py`
- [x] 8.4 Celery `integrations.volunhub.sync_all` / `sync_one`; `manage.py sync_volunhub [--user <id>]`
- [x] 8.5 Merge service:
      1. re-point the link;
      2. move the old project's tasks through `save()`;
      3. delete the old project once it's empty;
      4. set `auto_created=False`.

## 9. Task API surface
- [x] 9.1 `tasks/api/serializers.py`: a `volunhub` field (`{url, state, removed_reason, error}` or
      null) via `getattr(task, "volunhub_link", None)`. Include it in `TaskListSerializer`, so
      WebSocket payloads carry it.
- [x] 9.2 `tasks/views.py`: `select_related("volunhub_link")`

## 10. Frontend (`frontend/src/app/integrations/`)
- [x] 10.1 `volunhub.service.ts` + `volunhub.model.ts` (+ spec)
- [x] 10.2 `volunhub-settings` card on `/settings/integrations`, next to the Notion card:
      - status and last sync; connect, sync now, disconnect;
      - handle `?volunhub=connected|error`;
      - banners for reauth, read-only, and content push disabled (with retry);
      - the disclosure block.
- [x] 10.3 Project mapping table with a "merge into…" project picker
- [x] 10.4 Badges in task list + detail: "VolunHub" (links to `/proiecte/task-uri/<id>/`) and
      "Removed from VolunHub (reason)"; `volunhub` added to the `Task` type

## 11. Tests (`integrations/volunhub/tests/`)
- [x] 11.1 `fakes.py`: an in-memory VolunHub with the real transition graph, pagination, a stale
      `completed` column, `+03:00` datetimes, and switchable `PATCH` `403`
- [x] 11.2 OAuth:
      - DCR scope fail-closed;
      - client reused across users;
      - PKCE correctness;
      - state single-use and expiry;
      - read-only on missing write scope;
      - refresh rotation persisted;
      - concurrent refresh sends one request;
      - `invalid_grant` → `needs_reauth`.
- [x] 11.3 Client: path allow-list, retry/backoff, partial-listing failure
- [x] 11.4 Mapping: every state in both directions, `givenup`, no-workflow, priority, timezone
      normalization
- [x] 11.5 Sync:
      - first import;
      - remote edit applied;
      - local edit pushed (only changed fields);
      - conflict → Organizer wins;
      - no echo on the next run;
      - two-step reopen;
      - `409` isolated and retried;
      - `PATCH` `403` → status-only;
      - removal deleted/unassigned/probe-error;
      - re-attach;
      - local-delete tombstone never re-imported or deleted upstream;
      - disconnect/reconnect without duplicates.
- [x] 11.6 Projects: auto-create, shared across users, rename while auto-created, merge moves tasks
      and deletes the empty project, no re-create after a local delete, local move kept
- [x] 11.7 Views: auth required, owner scoping, tokens never serialized; `test_routing.py`: the
      callback resolves to Django and is excluded by ngsw
- [x] 11.8 Frontend specs for the service, the settings card and the task badge

## 12. Docs & validation
- [x] 12.1 `docs/volunhub.md`:
      - setup and nginx (`/integrations/` is already proxied);
      - field mapping and the status table;
      - conflict rule, removal, projects/merge, Notion exclusion;
      - troubleshooting.

      Also update `CLAUDE.md` (Architecture + commands) and `README.md`.
- [ ] 12.2 Optional, separate PR in the VolunHub repo: the upstream fixes listed in design.md
      (deferred — not part of this change; the prompt for it was handed over separately)
- [x] 12.3 `openspec validate add-volunhub-task-sync --strict`; `uv run ruff check .`;
      `uv run python manage.py test integrations tasks`; frontend `npm test`
