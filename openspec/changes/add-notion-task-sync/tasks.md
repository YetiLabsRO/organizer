# Tasks: Two-way Notion task sync

## 1. Dependencies, config & app scaffold
- [x] 1.1 Add `httpx` and `cryptography` to `pyproject.toml`; `uv lock`; regenerate `requirements.txt`
      with `uv export`
- [x] 1.2 Create the `integrations/` namespace package and the `integrations/notion/` app (`AppConfig`,
      label `notion`); add `integrations.notion` to `INSTALLED_APPS`
- [x] 1.3 Add config to `settings.py` + `.env.example`: `NOTION_CLIENT_ID`, `NOTION_CLIENT_SECRET`,
      `NOTION_REDIRECT_URI`, `NOTION_API_VERSION` (default `2025-09-03`), `NOTION_SYNC_MINUTES`
      (default 10), `NOTION_FULL_SYNC_HOURS` (default 24), `FRONTEND_BASE_URL`,
      `INTEGRATIONS_TOKEN_KEY` (Fernet; dev fallback derived from `SECRET_KEY`)
- [x] 1.4 Implement `integrations/crypto.py` — Fernet encrypt/decrypt helpers for token fields (shared
      with future integrations)

## 2. OAuth client (`oauth.py`)
- [x] 2.1 Authorize-URL builder — `response_type=code`, **`owner=user`**, the exact registered
      `redirect_uri`, and `state`. PKCE is undocumented for this flow — do not depend on it; `state` is
      the CSRF defence
- [x] 2.2 Code exchange at `POST https://api.notion.com/v1/oauth/token` using **HTTP Basic**
      (`base64(client_id:client_secret)`), not `client_secret_post`
- [x] 2.3 Persist `bot_id`, `workspace_id`, `workspace_name`, `workspace_icon` from the token response —
      `bot_id` is what echo suppression depends on
- [x] 2.4 Refresh (`grant_type=refresh_token`, same Basic auth); **persist the rotated `refresh_token`**
      from every refresh response; map `invalid_grant` → `needs_reauth`
- [x] 2.5 Do **not** precompute expiry — no `expires_in` is returned; refresh reactively on `401`.
      Record when no refresh token was issued so the UI can warn

## 3. Models & migrations
- [x] 3.1 `NotionOAuthFlow` (state, user, created_at — single-use, 10-min TTL)
- [x] 3.2 `NotionConnection` (encrypted tokens, bot_id, workspace identity, status ∈ `active` /
      `needs_reauth` / `schema_drift` / `unprovisioned`, last_synced_at, last_full_sync_at, last_error)
- [x] 3.3 `NotionDatabase` (OneToOne with connection; `database_id`, **`data_source_id`**,
      `parent_page_id`, `property_ids` JSON, `pull_watermark`, `bootstrap_state`, `bootstrap_cursor`)
- [x] 3.4 `NotionTaskLink` (database FK, `task` OneToOne **null=True / SET_NULL** so a locally-deleted
      task leaves a tombstone, `notion_page_id`, `notion_last_edited_time`, `local_changed_at`) +
      unique `(database, notion_page_id)`
- [x] 3.5 `makemigrations` + `migrate`

## 4. Account-linking flow (`views.py`, `urls.py`)
- [x] 4.1 DRF `POST /api/integrations/notion/connect/` — create the pending flow bound to the user,
      return the authorize URL
- [x] 4.2 Plain Django `GET /integrations/notion/callback/` — validate + consume `state` (reject unknown,
      expired, reused), exchange the code, store tokens against the bound user, redirect into the SPA
- [x] 4.3 DRF `GET /api/integrations/notion/status/` and `POST /api/integrations/notion/disconnect/`
      (delete credentials and links; no revocation endpoint exists — the UI explains manual revocation)
- [x] 4.4 Wire routes in `organizer/urls.py`

## 5. Notion API client (`client.py`)
- [x] 5.1 `NotionClient` bound to a `NotionConnection`: `Authorization: Bearer`, and the required
      **`Notion-Version`** header pinned to `NOTION_API_VERSION`
- [x] 5.2 **Token-bucket pacer at 3 requests/second** (Notion's limit is a documented *average*, so pace
      rather than react)
- [x] 5.3 `429` → honour `Retry-After`; `5xx`/`529` → jittered exponential backoff with a retry cap;
      `401` → one refresh-and-retry
- [x] 5.4 `search_pages()` — `POST /v1/search` filtered to pages, for the parent-page picker
- [x] 5.5 `create_database(parent_page_id, schema)` — `POST /v1/databases` with
      `initial_data_source.properties`; capture the returned `database_id` **and** `data_source_id`
- [x] 5.6 `retrieve_data_source()` / `update_data_source()` — `GET|PATCH /v1/data_sources/{id}`, for
      drift checks and option seeding
- [x] 5.7 `query_data_source(filter=None, start_cursor=None)` — **`POST /v1/data_sources/{id}/query`**
      (a database id is rejected here), paging on `next_cursor`
- [x] 5.8 `create_page` / `update_page` / `trash_page` — `POST /v1/pages` with
      `parent: {type: "data_source_id"}`; `PATCH /v1/pages/{id}` for properties and for
      `in_trash: true`. A page's parent can never be changed — assert we never attempt it

## 6. Schema & provisioning (`schema.py`)
- [x] 6.1 Define the property schema: `Name` (title), `Description` (rich_text), `Status` (select),
      `Done` (checkbox), `Completed at` (date), `Priority` (select), `Start` (date), `Deadline` (date),
      `Estimate (min)` (number), `Today` (checkbox), `Tags` (multi_select), `Project` (select),
      `Parent task` (self-relation, `single_property`), `Last edited by` (last_edited_by)
- [x] 6.2 DRF `GET /api/integrations/notion/pages/` (shared pages) and
      `POST /api/integrations/notion/provision/` (create the database under the chosen page)
- [x] 6.3 Record `property_ids` at provisioning so properties are addressed **by id**, surviving renames
- [x] 6.4 Drift check before each sync: a missing required property → `schema_drift`, sync paused, no
      writes; expose a repair action
- [x] 6.5 Seed select/multi-select options (statuses, priorities, the user's projects and tags) before
      bootstrap; map `Tag.color` hex → nearest colour in Notion's fixed palette

## 7. Field mapping (`mapping.py`)
- [x] 7.1 Outbound: `TaskItem` → Notion property values, chunking `description` into ≤2000-char rich-text
      objects; log (never silently truncate) anything Notion rejects as oversized
- [x] 7.2 Inbound: Notion property values → local fields; never touch the page body
- [x] 7.3 `completed_date` written via post-save `queryset.update()` to defeat `MonitorField.pre_save`
      restamping it to `now()` — which also avoids bumping `changed_date` via `auto_now`
- [x] 7.4 `Project` / `Tags` resolved against **existing** records only (case-insensitive); unknown
      values ignored + logged, never auto-created (both models are global, not per-user)
- [x] 7.5 `parent_task` ⇄ `Parent task` self-relation, resolved through `NotionTaskLink`
- [x] 7.6 Note in code that `TaskItem.save()` copies project tags onto the task, so an inbound project
      change legitimately adds tags that later flow back to Notion

## 8. Sync engine (`sync.py`)
- [x] 8.1 **Bootstrap**: upload every task with `owner=connection.user` in `pk` order, advancing
      `bootstrap_cursor`; resumable after interruption without duplicates; gates incremental sync until
      `bootstrap_state=done`
- [x] 8.2 **Pull**: `last_edited_time on_or_after (watermark − 120s)`, sorted ascending, paged. The
      2-minute overlap is required because Notion rounds `last_edited_time` **down to the minute**
- [x] 8.3 **Echo suppression**: skip any page whose `last_edited_by.id == connection.bot_id`
- [x] 8.4 **Push** in order: `task IS NULL` links → trash upstream; unlinked local tasks scoped
      `owner=connection.user` → create page; changed linked tasks → patch page
- [x] 8.5 Second pass for `parent_task` relations, so a parent's page exists before children link to it
- [x] 8.6 **Re-stamp both watermarks after every write on both sides** so the engine never reads its own
      write as a user edit (the ping-pong invariant)
- [x] 8.7 Conflict resolution: most-recent wins; **same-minute tie → Organizer wins**; log every outcome
- [x] 8.8 Applies are **idempotent** — re-processing a page inside the overlap window writes nothing
- [x] 8.9 **Full reconciliation** every `NOTION_FULL_SYNC_HOURS`: unfiltered walk of the data source;
      links missing from the sweep confirmed with `GET /v1/pages/{id}` before deleting the local task
      (the query API returns non-archived rows only and cannot filter `in_trash`)

## 9. Triggers
- [x] 9.1 Celery task + beat schedule (`NOTION_SYNC_MINUTES`), each connection in its own transaction so
      one failure cannot abort the batch — mirroring `tasks/tasks.py`
- [x] 9.2 `manage.py sync_notion [--user <id>] [--full]`
- [x] 9.3 DRF `POST /api/integrations/notion/sync/` — **enqueues** for the requesting user only (never
      inline: bootstrap alone can exceed any request timeout)

## 10. Frontend (`frontend/`)
- [x] 10.1 `/settings/integrations` route + standalone component (signals, `OnPush`, `--org-*` tokens):
      connection status, Connect, Disconnect, Sync now, and the `needs_reauth` reconnect prompt
- [x] 10.2 Provisioning step: list shared Notion pages, pick a parent, create the database; explain the
      "no shared pages" case; show bootstrap progress; link to the created database
- [x] 10.3 Notion source badge on mirrored tasks in list + detail, linking to the Notion page
- [x] 10.4 Disclosure copy: the page body is never synced; deletion on either side removes the task on
      the other; projects/tags are matched against existing ones, not created; manual revocation on
      disconnect; `schema_drift` repair prompt

## 11. Tests (`integrations/notion/tests/`)
- [x] 11.1 OAuth: authorize URL carries `owner=user`, exact redirect URI and `state`; exchange uses HTTP
      **Basic**; rotated refresh token persisted; `invalid_grant` → `needs_reauth` (Notion HTTP mocked)
- [x] 11.2 Linking: connect creates a pending flow; callback binds tokens to the right user via `state`;
      unknown / expired / reused `state` rejected
- [x] 11.3 Provisioning: database created under the chosen page; `data_source_id` stored and used for
      row calls; `property_ids` recorded; a renamed property still maps; a deleted property →
      `schema_drift` and no writes
- [x] 11.4 Bootstrap: uploads all of the user's tasks; an interrupted run resumes without duplicates;
      incremental sync does not run before it completes
- [x] 11.5 Pull: overlap window applied; paging followed beyond one page; unlinked page creates a local
      task owned by the connection user; re-applying an already-applied page writes nothing
- [x] 11.6 **Echo suppression**: a page whose `last_edited_by` is our `bot_id` is skipped
- [x] 11.7 **No ping-pong**: applying an inbound change does not cause the next run to push it back
- [x] 11.8 Conflict: different-minute → most recent wins; **same-minute → Organizer wins**
- [x] 11.9 Push: unlinked local task creates a page; locally-deleted task (`task IS NULL`) trashes its
      page; parent relations resolved in the second pass
- [x] 11.10 Full reconciliation: a page absent from the sweep and confirmed trashed deletes the local
      task; one absent but **not** trashed is kept
- [x] 11.11 Mapping: `completed_date` keeps Notion's timestamp (not `now()`); unknown project/tag values
      ignored and logged; long descriptions chunked
- [x] 11.12 Scoping: push only ever sends tasks with `owner=connection.user` (projects and tags are
      global — a second user's task in the same project must not leak); all endpoints owner-scoped and
      authenticated
- [x] 11.13 Rate limiting: `429` with `Retry-After` is honoured; one failing connection does not abort
      the scheduled batch

## 12. Docs
- [x] 12.1 `docs/notion.md` — creating the public Notion integration, the exact redirect URIs, the
      page-picker consent model, API version `2025-09-03` (databases vs data sources), and the sync/beat
      setup
- [x] 12.2 Update `.env.example` (done in 1.3), `CLAUDE.md`, `README.md`
- [x] 12.3 `openspec validate add-notion-task-sync --strict` passes; `ruff check` + `ruff format` clean;
      `manage.py test` green
