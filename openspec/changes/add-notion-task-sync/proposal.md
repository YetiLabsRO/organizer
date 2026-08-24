# Change: Two-way Notion task sync (Organizer-owned database)

## Why
Notion is where a lot of thinking already happens — meeting notes, project docs, weekly reviews. Today
Organizer's tasks are invisible there, so planning in Notion means retyping tasks that already exist,
and anything captured in Notion never reaches the app that actually tracks it. We want a linked user's
tasks to live in **both** places: edit a task in Notion and Organizer picks it up, edit it in Organizer
and Notion follows.

Unlike a Google Tasks or VolunHub sync, this integration is **not** adapting to a foreign schema. The
sync **creates its own Notion database from scratch, empty**, and owns its property schema. That single
fact removes almost all of the field-fidelity problems that plague thin-surface integrations: because
we design the schema, priority, workflow status, tags, project, start date, estimated time and the
parent/child relationship all get a real column. The interesting problems move elsewhere — echo
suppression, Notion's minute-rounded timestamps, and the fact that a Notion page can never change parent.

## What Changes
- Add a new **`integrations/notion/` Django app** acting as an OAuth 2.0 **confidential client** of
  Notion (authorization code, HTTP **Basic** client authentication, `owner=user`; Notion offers **no**
  dynamic client registration, so the integration is registered by hand once, and its public-integration
  flow documents no PKCE parameters — `state` carries the CSRF burden).
  - **Per-user account linking**: the SPA starts the flow; an unguessable single-use `state` binds the
    flow to the Organizer user, since the OAuth callback is a plain browser navigation carrying neither
    the SPA's DRF token nor a Django session.
  - **Token storage**: per-user access/refresh tokens **encrypted at rest** (Fernet). Notion's token
    response carries no `expires_in`, and its refresh tokens **rotate** — the new one is persisted on
    every refresh, and `invalid_grant` flips the connection to `needs_reauth`.
  - The token response's **`bot_id`** is stored: it is what makes echo suppression possible (below).
- Add a **Notion API client** (`httpx`) pinned to API version **`2025-09-03`** — the version in which
  databases were split into databases + **data sources**, so all row-level calls go to
  `/v1/data_sources/{id}/…`, not `/v1/databases/{id}/…`. Includes a **3 requests/second pacer** and
  `Retry-After`-honouring backoff on `429`.
- Add **provisioning**: the user picks one Notion page they shared with the integration during consent,
  and Organizer **creates the task database under it**, with an Organizer-designed schema. There is no
  mapping UI and no existing-database adoption — the database starts **empty** and is owned by the sync.
- Add a **bootstrap push**: because the database starts empty, the first sync is a one-way upload of
  every existing task the user owns. It is resumable and rate-paced, tracked by its own cursor, and
  runs in Celery rather than inline in a request.
- Add a **two-way sync engine**:
  - **Pull (Notion → Organizer):** incremental `POST /v1/data_sources/{id}/query` filtered on
    `last_edited_time on_or_after (watermark − 2 min)`, paged on `next_cursor`. Because Notion rounds
    `last_edited_time` **down to the minute**, the overlap window and idempotent applies are mandatory,
    not defensive.
  - **Push (Organizer → Notion):** creates, updates and trashes pages from local changes.
  - **Echo suppression:** every page carries `last_edited_by`; a page whose last editor is our own
    `bot_id` is our own write and is skipped. This is the primary defence against sync ping-pong, with
    the watermark pair as backup.
  - **Conflict resolution:** per-link watermarks decide which side moved; when both did, the more
    recent change wins — and because Notion's timestamp is minute-rounded, a **same-minute tie resolves
    in Organizer's favour** (it is the finer-grained clock and the source of truth).
  - **Deletion:** a locally deleted task trashes its Notion page. Detecting the reverse is a
    **full-reconciliation** job, because Notion's query endpoint cannot filter on `in_trash` and returns
    only non-archived rows by default.
- Add **sync triggers**: a Celery-beat schedule (the repo already runs Celery for recurring tasks), a
  `sync_notion` management command, and an authenticated "sync now" endpoint.
- Add **frontend** surface (Angular): an integrations settings screen to connect/disconnect, choose the
  parent page, watch bootstrap progress and sync now; plus a Notion badge linking a mirrored task to its
  Notion page.

Out of scope: **Notion webhooks** (they exist, but a subscription is created and verified by hand in
Notion's developer dashboard rather than through the API, and delivery is explicitly *at-most-once* — so
polling is required for correctness anyway; webhooks would only reduce latency, and can be added later
without schema change). Also out of scope: syncing `TaskComment`s to Notion comments; adopting a
pre-existing Notion database; syncing Organizer projects or tags as their own Notion databases; and
free-form page **body** content, which is deliberately left as the user's own un-synced scratch space.

## Impact
- **Affected specs:** **notion-integration** (new capability), **web-frontend** (adds integration
  management UI + external-source indication).
- **Affected code:**
  - `pyproject.toml` / `uv.lock` / `requirements.txt` — add `httpx` and `cryptography`.
  - `organizer/settings.py` — register the app; add `NOTION_*` + `INTEGRATIONS_TOKEN_KEY` config and the
    beat schedule entry.
  - `organizer/urls.py` — mount the DRF endpoints and the plain browser callback view.
  - New `integrations/notion/` package + migrations.
  - `frontend/` — integrations settings screen, provisioning flow, source badge.
  - `.env.example`, `CLAUDE.md`, `README.md`, `docs/notion.md` — config keys and integration setup.
  - Tests under `integrations/notion/tests/`.
- **New per-user data:** OAuth credentials for a third-party workspace, encrypted at rest and destroyed
  on disconnect.
- **Shared groundwork:** this change introduces the `integrations/` namespace package, `crypto.py`
  (Fernet helpers) and the generically-named `INTEGRATIONS_TOKEN_KEY` setting. The pending Google Tasks
  and VolunHub sync proposals assume the same three; whichever lands first creates them and the others
  reuse them.
- **Operational prerequisite:** a **public** Notion integration must be created once in Notion's
  developer settings, with the exact redirect URI registered. Users then authorize it and, during
  Notion's own consent screen, **select which pages the integration may access** — Organizer can only
  create its database under a page the user picked there.
