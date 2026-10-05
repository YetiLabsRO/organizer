# Design: Two-way VolunHub task sync

## Context
Organizer becomes an OAuth 2.1 **public client** of VolunHub's confined task-aggregator API. The
structure copies `integrations/notion/`: a per-provider app; a `<Provider>OAuthFlow` that binds
`state` to the user; encrypted tokens through `integrations/crypto.py` (`INTEGRATIONS_TOKEN_KEY`); a
`/api/integrations/<p>/{connect,status,disconnect,sync}/` API; a plain `/integrations/<p>/callback/`
that redirects to `/settings/integrations?<p>=…`; a Celery beat entry; and a `sync_<p>` command.

The design rests on facts checked in the VolunHub source, several of which its own handover doc
(`docs/task-aggregator-api.md`) gets wrong:

| Fact | Consequence for us |
| --- | --- |
| `?mine=true` means **personally assigned** (`PROJECTS:TASK_ASSIGNEE`), not reporter. Team-only assignments are excluded. A restricted token always gets the "mine" scoping. | We import exactly "tasks assigned to me". The disclosure says so. |
| A status change (`transition_task`) **does not bump `changed_date`**. Neither do assign or unassign. | `changed_date` cannot drive incremental sync, so we diff full snapshots. |
| The listing's `completed` column is **stale**: transitions never write it. `state_name` (a Romanian label) and the `/status/` response are authoritative. | Derive completion from `state_name`. Ignore `completed`. |
| No changed-since filter, no tombstones, no webhooks. Pages are 50 rows, with `?page=N`. The default ordering is `-start_date`, which is nullable and has no tiebreaker. | Read the full listing with `ordering=id` each run. Detect removals by diffing. |
| Workflow: new tasks start in Draft. Draft→{Planned, Blocked, Finished}; Planned→{In progress, Blocked, Finished}; In progress→{Finished, Blocked, Planned}; **Finished→Planned only**; Blocked→any. Same-state requests are idempotent `200`s. Errors: `409` unreachable, `400` unknown state or no workflow (`state_name == ""`). | Status pushes plan a route, going through `planned` when needed. |
| The confinement middleware allows **any method** on `/api/v1/projects/tasks…` when the token has `mcp:tasks:write`. So `PATCH /tasks/<id>/` works (title, description, start/end, deadline, estimated time, priority) and returns the full task. `GET /tasks/<id>/` resolves any task the user can *view*, not just "mine". | Enables content write-back and removal probing. Undocumented, so it must degrade cleanly (D6). |
| Datetimes are ISO-8601 in `Europe/Bucharest` (`+03:00`), with microseconds left out when zero. `deadline` is the real due date. `start_date`/`end_date` are a planned work window. Priority is 1 Joasă, 2 Normală, 3 Înaltă. `estimated_time` is in minutes. `description` is Markdown. | Mapping table (D4). Normalize to UTC before comparing. |
| DCR is open and unauthenticated. A request for exactly a subset of the restricted scopes pins the client to that subset; omitting scope, or adding another scope, gives a **full-scope** client. Consent is shown on **every** authorization, and the user can untick scopes. | Register once and fail closed on the returned scope. Check the granted scope on every token response. |
| Access token 3600 s. Refresh token 30 d, sliding, **rotated**: the old one is revoked, with no reuse grace and no lock. `/revoke` (with `client_id`) revokes all of a client+user's tokens. | Serialize refreshes per connection. Revoke on disconnect. |
| No rate limits on the API or on OAuth. Each write notifies the task's watchers. | Be polite anyway (back off on 429/5xx). Push only changed fields. |

## Goals / Non-goals
- **Goals:**
  - per-user linking;
  - import assigned tasks as native Organizer tasks;
  - push edits (content and status) back;
  - never create or delete in VolunHub;
  - never lose local data;
  - one external owner per task.
- **Non-goals:**
  - creating or deleting VolunHub tasks;
  - tags, assignees, teams, watchers, comments, subtasks and `kind`;
  - pushing project moves (the update serializer has no project field);
  - a provider framework.

## D1 — Client registration: lazy, once per (base URL, redirect URI), fail closed
`VolunHubOAuthClient` stores `base_url`, `redirect_uri`, `client_id`, `scope`, the discovered
endpoints and `registered_at`, unique on `(base_url, redirect_uri)`. Each connection keeps a foreign
key to the client that issued its tokens, so refreshes keep using it. The first connect registers inside a transaction holding a row lock,
so two concurrent connects can't create two clients (a Postgres advisory lock). Changing `VOLUNHUB_REDIRECT_URI` makes the next
connect register a new client.

Registration request:
```json
{"client_name": "Organizer", "redirect_uris": ["<VOLUNHUB_REDIRECT_URI>"],
 "token_endpoint_auth_method": "none", "grant_types": ["authorization_code", "refresh_token"],
 "response_types": ["code"], "scope": "mcp:tasks:read mcp:tasks:write"}
```
If the response's `scope`, read as a set, is not exactly `{mcp:tasks:read, mcp:tasks:write}`, or the
field is missing, the client is **not persisted** and connect fails with a clear error. A full-scope
client is a credential we refuse to hold. `VOLUNHUB_CLIENT_ID` overrides registration for operators
who register out of band.

The discovery metadata lists only `client_secret_*` under `token_endpoint_auth_methods_supported`, yet
public clients work. So we do not validate against that list.

## D2 — Linking flow (SPA uses DRF token auth)
This is the Notion flow plus PKCE:
1. `POST /api/integrations/volunhub/connect/` (DRF token) creates
   `VolunHubOAuthFlow{state=token_urlsafe(32), code_verifier, user}`, with a 10-minute TTL and single
   use. It returns `{authorize_url}`, carrying `client_id`, the exact `redirect_uri`,
   `scope=mcp:tasks:read mcp:tasks:write`, `code_challenge` (S256) and `state`.
2. The SPA sets `window.location.href`, and VolunHub shows login and consent.
3. `GET /integrations/volunhub/callback/` is plain Django, unauthenticated and `@require_GET`. It
   handles `error`, consumes `state`, exchanges the code (`client_id` + `code_verifier`, **no
   secret**), and stores the tokens and `granted_scope`. It then redirects to
   `{FRONTEND_BASE_URL}/settings/integrations?volunhub=connected|error&reason=…`.
4. Granted scope:
   - missing `mcp:tasks:read`: the link is refused (`reason=insufficient_scope`);
   - missing only `mcp:tasks:write`: the connection is stored **read-only**, so nothing is pushed
     and every field is import-only. The UI says so and offers a reconnect.

## D3 — Data model (`integrations/volunhub/models.py`)
- **`VolunHubOAuthClient`**: see D1.
- **`VolunHubOAuthFlow`**: `state` (unique), `code_verifier`, `user` FK, `created_at`.
  `consume(state)` returns the flow or None. Unknown, expired and replayed states are
  indistinguishable on purpose.
- **`VolunHubConnection`**:
  - `user` OneToOne (`related_name="volunhub_connection"`);
  - `access_token_encrypted`, `refresh_token_encrypted` and `access_token_expires_at`;
  - `granted_scope`;
  - `status` (`active` | `needs_reauth`);
  - `content_push_enabled` (bool, default True; see D6);
  - `last_error`, `connected_at`, `last_synced_at`.
  - Derived properties: `can_write` (scope includes write) and `pushes_content` (`can_write and
    content_push_enabled`).
- **`VolunHubProjectLink`** (**global**, because `Project` is global):
  - `external_id` (unique), `external_slug`, `external_name`;
  - `project` FK → `tasks.Project`, `SET_NULL`;
  - `auto_created` (bool: the project was created by the sync and hasn't been merged).
- **`VolunHubTaskLink`**:
  - `user` FK, `external_id`, unique on `(user, external_id)`;
  - `task` OneToOne → `tasks.TaskItem`, `null=True`, `SET_NULL`, `related_name="volunhub_link"`;
  - `state` (`active` | `removed`), `removed_reason` (`unassigned` | `deleted` | `disconnected`) and
    `removed_at`;
  - `snapshot` JSON: the last agreed values, in Organizer representation (D4);
  - `external_project_id`, `last_error` and `last_synced_at`.

Links hang off the **user**, not the connection, so they survive a disconnect and a reconnect can
re-attach to the same local tasks. VolunHub task ids are global, so matching by id is safe. A link
whose `task` is null is a **local-delete tombstone**: the task is not re-imported, and nothing is
deleted upstream.

## D4 — Field mapping (both directions)
| Organizer `TaskItem` | VolunHub task | Notes |
| --- | --- | --- |
| `title` | `title` | ≤ 1024 on both sides |
| `description` | `description` | Markdown passthrough. Normalize `None`↔`""` and `\r\n`→`\n` before comparing |
| `start_date` | `start_date` | Aware datetimes, compared in UTC |
| `end_date` (Organizer's deadline) | `deadline` | VolunHub `end_date` (end of the work window) is not mapped |
| `estimated_time` | `estimated_time` | Minutes on both sides |
| `priority` LOW=1 / NORMAL=2 / HIGH=4 | `priority` 1 / 2 / 3 | Bijective |
| `status` + `completed` | `state_name` → state | See below |
| `project` | `project_id/slug/name` (inline) | **Import-only**, via `VolunHubProjectLink` (D7) |

Not synced: tags, `for_today`, `parent_task`, `order`, `template` (Organizer-only), and `kind`,
`actual_time`, assignees, teams and watchers (VolunHub-only).

**State labels → slug**: Ciornă→`draft`, Planificat→`planned`, În lucru→`in_progress`,
Finalizat→`finished`, Blocat→`blocked`. An empty or unknown label means "no workflow": status is not
synced for that task, in either direction.

**Import (VolunHub → Organizer status):**
- `draft`, `planned` → `idea`;
- `in_progress` → `inprogress`;
- `blocked` → `blocked`;
- `finished` → `completed=True`, `status` left as it is.
- Any non-finished state → `completed=False`.

**Write-back (Organizer → VolunHub state):**
- `completed=True` → `finished`.
- Otherwise:
  - `inprogress` → `in_progress`;
  - `blocked` → `blocked`;
  - `idea` → `planned`;
  - `givenup` → **not pushed**: there is no equivalent, so it stays local. The disclosure says so.
- **Route planning**: if the target can't be reached directly from the snapshot state (draft →
  in_progress, finished → in_progress or blocked), send `planned` first. `planned` is reachable from
  every state except itself, and it reaches every target we ever push. A `409` on either step is
  recorded on the link as `last_error`.

The snapshot stores values **in Organizer representation**, i.e. after the import mapping. Remote and
local changes are then both detected by comparing like with like. So a VolunHub `draft→planned` change
(both map to `idea`) is correctly a no-op, and a task sitting in `draft` is never pushed just because
`idea` maps back to `planned`.

## D5 — Sync algorithm (`sync.py`, one run per connection)
0. Take a per-connection Postgres advisory lock (`pg_try_advisory_lock`). If it is held, skip the
   run, so a beat run and a "Sync now" never overlap. Make sure the access token is fresh (D8).
1. **List.** Read `GET /api/v1/projects/tasks/?mine=true&ordering=id`, following `next` to the end.
   If any page fails, **abort the run**: no merges, no removals. We never act on a partial listing.
2. **Per remote task**, keyed by `(user, external_id)`:
   - **No link:** create a local `TaskItem` (`owner=user`) from the mapped values, resolve its project
     (D7), and create an active link with `snapshot = mapped values`. Task and link are written in
     one transaction, so the Notion exclusion holds from the first commit.
   - **Tombstone link** (`task=None`): skip.
   - **Removed link:** **re-attach**: set `state=active` and clear the reason, then merge as below.
   - **Active link, three-way merge per synced field:**
     - `base` = the snapshot value, `remote` = the mapped remote value, `local` = the current task
       value.
     - Only `remote≠base` → apply locally.
     - Only `local≠base` → push.
     - Both changed, and `remote==local` → just update the snapshot.
     - Both changed, values differ → **Organizer wins**: push, and log a conflict.
     - A field that **can't be pushed** right now (read-only connection, content field while content
       push is disabled, status on a no-workflow task) gives way: **VolunHub wins** when it changes.
       A local edit to such a field is kept only until VolunHub changes the same field.
     - The one exception is a local `givenup` status. It is never pushed and never overwritten: a
       deliberate local choice. Project is outside the merge entirely (D7).
   - **Order of writes:**
     1. Apply local changes with one `task.save()`, which broadcasts over the WebSocket.
     2. `PATCH` only the changed content fields.
     3. Run the status route.
     4. Rebuild the snapshot from the `PATCH` and `/status/` responses for the fields they confirm, and
        from the merged values for the rest.

     A failed push leaves `base` unchanged for that field, so it is retried next run. The error is
     kept in `last_error`.
3. **Removals.** For each **active** link with a live task whose id was absent from the complete
   listing, probe `GET /api/v1/projects/tasks/<id>/`:
   - `404` → `removed`, reason `deleted`. This also covers "no longer visible to you", which we can't
     tell apart.
   - `200` → `removed`, reason `unassigned`.
   - Anything else, or a network error → leave it alone and retry next run.

   Removal never touches the local task's fields; it only marks the link. For tombstone links absent
   from the listing, delete the link row.
4. Stamp `last_synced_at`, clear `last_error`, and return a report (created / updated / pushed /
   conflicts / removed / reattached / errors).

**Echo suppression is automatic.** Whatever we push becomes the new `base`, so on the next run the
remote value equals `base` and nothing is applied. Our own `save()` bumping `TaskItem.changed_date` is
harmless, because the merge compares values, not timestamps. So the Notion integration's
watermark-re-stamping hazard doesn't exist here.

**Why Organizer wins true conflicts** (instead of most-recent-wins as in Notion): VolunHub provides no
trustworthy change time for status (`changed_date` isn't bumped) and none per field. With a 10-minute
poll, true same-field conflicts are rare. A deterministic rule beats a guess.

**Cost:** one full listing per run, at 50 rows per page, which is fine at personal scale. Per-task
cost is one `PATCH` and up to two `/status/` calls, only when something changed.

## D6 — Content write-back must degrade cleanly
VolunHub's docs say the restricted token is status-only. The middleware disagrees today, but the
VolunHub operator may tighten it. Assignees always pass VolunHub's `can_edit_task`, so a `403` on a
`PATCH` to a task in the user's own list can only mean policy. On such a `403`:
- set `connection.content_push_enabled = False`;
- record the reason;
- carry on with status pushes;
- treat content fields as import-only from then on.

The UI shows a banner. Reconnecting, or a "retry content sync" action, resets the flag. A `400`
(validation) stays per-task, in `last_error`.

## D7 — Projects: auto-create, then merge
Projects come from the **inline** `project_id/slug/name` on each task, because
`projects/?mine=true` uses a different ownership rule and misses projects of tasks assigned to us. On
first sight of a VolunHub project id:
- create `Project(title=project_name)`;
- create `VolunHubProjectLink(auto_created=True)`;
- give the task that project.

Later runs work like this:
- **Re-use:** the same external id always resolves to the link's project. The link is global, so two
  Organizer users on the same VolunHub project share one local project.
- **Rename:** when `project_name` changes, update `external_name`. The local project title is renamed
  only while `auto_created` is true.
- **Merge:** `POST /api/integrations/volunhub/projects/<external_id>/merge/ {project_id}`:
  1. re-points the link to an existing local project and sets `auto_created=False`;
  2. moves every task of the old auto-created project to the target, through `save()` so the moves
     broadcast;
  3. deletes the old project once it has no tasks left.

  Merging again into another project is allowed, and is how a merge gets undone. Only users who have
  a task link referencing that external project may list or merge it.
- **Local deletion of the project** (link `project=None`): the affected tasks import project-less,
  and the UI offers a merge target. A project is never re-created behind the user's back.
- **Project changes on the task** are import-only. A local move to another project is kept, because
  local `project` is never compared against the snapshot. A move in VolunHub is applied.
- **Accepted side effect:** projects are global, so auto-created VolunHub projects are visible to
  every Organizer user. This is a personal deployment, and the user chose it.

## D8 — Tokens, refresh, client
- `client.py`: an `httpx` client that sends `Authorization: Bearer`.
  - It has an **allow-list** of the two path prefixes `/api/v1/projects/tasks` and
    `/api/v1/projects/projects`. Any other path raises before sending.
  - Errors: `401` → refresh once and retry. `429`/`5xx` → bounded exponential backoff, honouring
    `Retry-After`. Other `4xx` → typed `VolunHubAPIError(status_code, body)`.
- **Proactive refresh** when `access_token_expires_at` is under 60 s away, plus reactive refresh on a
  `401`.
  - **Refresh runs in `transaction.atomic()` with `select_for_update()` on the connection.** After
    taking the lock, re-read the row: if another worker has already refreshed, use its token. Without
    this, two concurrent refreshes present the same refresh token, and the loser gets
    `invalid_grant` even though nothing is wrong.
  - Persist the rotated refresh token and the new expiry, and re-check the granted scope (it may only
    narrow).
  - `invalid_grant` → `status=needs_reauth`. The run ends without raising.
- **Disconnect**:
  1. `POST /revoke` with the refresh token and `client_id`, best-effort. This revokes all of this
     client's tokens for that user.
  2. Delete the connection.
  3. Mark every active task link `removed` with reason `disconnected`.

  Tokens are never logged and never serialized.

## D9 — Interaction with Notion
`integrations/notion/sync.py` `_push` step 2, which creates pages for unlinked tasks, adds
`volunhub_link__isnull=True`. Any task with a VolunHub link, **active or removed**, is excluded.
- **Why include removed links:** a removed task can come back, through reassignment or a reconnect.
  If Notion had adopted it in the meantime, the task would have two external owners, fighting over
  content and deletion.
- **Cost:** a "removed from VolunHub" task stays out of Notion. Tombstone links have no task, so they
  don't matter here.
- **Coded defensively:** tasks that already have a Notion link are left alone by the VolunHub import,
  which only ever creates new tasks.

## D10 — Triggers & settings
- **Celery:**
  - `integrations.volunhub.sync_all`: on beat every `VOLUNHUB_SYNC_MINUTES`, default 10. It skips
    `needs_reauth` connections and isolates failures per connection.
  - `integrations.volunhub.sync_one`: queued by `POST /api/integrations/volunhub/sync/`, which returns
    `{queued: true}`.
- **Command:** `manage.py sync_volunhub [--user <id>]` runs inline.
- **Settings:**
  - `VOLUNHUB_BASE_URL` (default `https://volunhub.scout.ro`, must be https unless `DEBUG`);
  - `VOLUNHUB_REDIRECT_URI` (default `http://localhost:8000/integrations/volunhub/callback/`);
  - `VOLUNHUB_CLIENT_ID` (optional override);
  - `VOLUNHUB_SYNC_MINUTES`.
  - Token encryption reuses `INTEGRATIONS_TOKEN_KEY`.
- **Task URL** for the badge: `{VOLUNHUB_BASE_URL}/proiecte/task-uri/<id>/` (VolunHub
  `projects:task_detail`).

## Module layout
```
integrations/volunhub/
  apps.py  models.py  exceptions.py  oauth.py  client.py  mapping.py  sync.py
  serializers.py  views.py  urls.py  tasks.py
  management/commands/sync_volunhub.py
  migrations/0001_initial.py
  tests/ (fakes.py — an in-memory fake VolunHub with the real transition graph — plus
          test_oauth, test_client, test_mapping, test_sync, test_views, test_routing)
```

## Risks / trade-offs
- **Undocumented `PATCH` surface.** Mitigated by D6. Worth confirming with VolunHub that this is
  intended, or getting the doc fixed.
- **Label-based state parsing.** Renaming a Romanian label silently disables status sync for the
  affected tasks: they parse as "no workflow", which is logged, not destructive. The upstream fix
  would be to expose the state slug.
- **Full listing every run.** Linear in the number of assigned tasks. Fine at personal scale.
- **Watcher notifications.** Every push notifies VolunHub watchers. Pushing only changed fields keeps
  this to genuine edits.
- **Global projects.** Auto-created projects are visible to every Organizer user (accepted, D7).
- **Lost-update window.** VolunHub `PATCH` has no `If-Match`. A VolunHub edit made between our
  listing and our `PATCH` on the same field is overwritten. That needs a sub-second same-field race,
  so we accept it.

## Suggested VolunHub-side fixes (separate change in the VolunHub repo, not blocking)
1. Bump `TaskItem.changed_date` on workflow transitions and on assignment changes.
2. Keep the `completed` column in sync with the workflow, or compute it in the serializer.
3. Expose the state slug, e.g. `state: "in_progress"`, next to `state_name`.
4. Update `docs/task-aggregator-api.md`:
   - `mine` = assignee;
   - `PATCH`, `GET <id>` and the other task actions are reachable;
   - `deadline` and the other fields are returned;
   - a subset of the restricted scopes also confines the client.
5. Add a stable default ordering (`-start_date, id`).

None are required. If 1 and 3 land, a later change could switch to incremental listing.

## Resolved questions
- **Finished tasks on first connect:** imported. They arrive completed, so they're hidden from
  open-task views but still count in statistics.
- **VolunHub `end_date` as a fallback deadline:** not used. The mapping stays bijective
  (`end_date` ↔ `deadline` only).
