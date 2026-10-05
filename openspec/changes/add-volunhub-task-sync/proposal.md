# Change: Two-way VolunHub task sync (OAuth 2.1 public client)

## Why
VolunHub (`https://volunhub.scout.ro`) exposes a confined "task aggregator" API: an OAuth 2.1 token
scoped `mcp:tasks:read mcp:tasks:write` that reaches only the tasks and projects endpoints and only
sees the caller's own tasks. Users who work in VolunHub currently have to track the tasks assigned to
them there in a second tool. We want those tasks to live in Organizer like native tasks: imported into
the user's lists, with edits made in Organizer flowing back to VolunHub. Organizer never creates or
deletes anything in VolunHub; it only updates tasks that already exist there.

Organizer already has the *server* half of this handshake (django-oauth-toolkit behind `/mcp`) and a
working two-way integration to copy from (`integrations/notion/`). This change adds the *client*
half for VolunHub, following the Notion module layout and reusing `integrations/crypto.py`, `httpx`,
Celery beat and the `/settings/integrations` screen.

## What Changes
- **New `integrations/volunhub/` Django app (label `volunhub`)**, laid out like `integrations/notion/`
  (`models`, `oauth`, `client`, `mapping`, `sync`, `tasks`, `views`, `urls`, `serializers`,
  `exceptions`, management command, tests).
- **OAuth 2.1 public client**: endpoint discovery from `/.well-known/oauth-authorization-server`;
  **one-time RFC 7591 dynamic registration** per instance and redirect URI, with the client marked
  `token_endpoint_auth_method: "none"`. It requests exactly `mcp:tasks:read mcp:tasks:write`, and the
  registration fails closed unless VolunHub returns exactly that scope set. Authorization code with
  **PKCE S256**, a `state` bound server-side to the requesting user, and encrypted token storage.
  Access tokens are refreshed both proactively and on a `401`. **Refreshes are serialized per user**,
  because VolunHub rotates refresh tokens and revokes the old one. Disconnect revokes the tokens
  best-effort.
- **Two-way field sync with a stored snapshot.** VolunHub's `changed_date` is not bumped by status
  changes, its listing's `completed` column is stale, and it has no changed-since filter. So each run
  reads the user's **full** assigned-task listing and does a **per-field three-way merge**: the
  current VolunHub values and the current local values are each compared against the last value both
  sides agreed on (the snapshot).
  - Synced fields: title, description, start date, deadline, estimated time, priority, and status or
    completion.
  - A field changed on one side flows to the other. A field changed on both sides to different values
    keeps the **Organizer value** (logged).
  - Content is written back with `PATCH /api/v1/projects/tasks/<id>/`. Status is written with
    `POST …/status/`, which may take two steps through `planned` when the workflow has no direct
    transition.
  - Project membership is **import-only**.
- **Projects are auto-created and can be merged.** The first time a VolunHub project is seen, an
  Organizer `Project` is created for it and linked. The user can later **merge** that project into an
  existing local project: the link is re-pointed, its tasks move, and the auto-created project is
  deleted once empty.
- **Removal is detected but never destructive.** A linked task that drops out of the listing is
  probed. Whether VolunHub deleted it or unassigned the user, the local task is **kept, unlinked and
  marked "removed from VolunHub"** with the reason. If the task comes back, through reassignment or a
  reconnect, it is re-attached to the same local task. A task deleted in Organizer is never deleted in
  VolunHub; it just stops syncing.
- **Excluded from Notion.** The Notion push skips any task that carries a VolunHub link, so a task
  has at most one external owner.
- **Triggers**: Celery beat `integrations.volunhub.sync_all` (every `VOLUNHUB_SYNC_MINUTES`, default
  10), a queued "Sync now" endpoint, and `manage.py sync_volunhub [--user <id>]`.
- **Frontend**: a VolunHub card on `/settings/integrations` with these parts:
  - connect, disconnect and sync now;
  - banners for re-authorization, read-only and content-push-disabled states;
  - a project mapping/merge table;
  - a disclosure of the non-obvious behaviours.

  Tasks also get a VolunHub source badge linking to the task in VolunHub, and a "removed from
  VolunHub" badge for unlinked copies.

Out of scope: creating or deleting VolunHub tasks; syncing tags, assignees, teams, watchers,
comments, subtasks or `kind`; webhooks (VolunHub has none, so polling is the only option); a generic
multi-provider framework.

## Impact
- **Affected specs:**
  - **volunhub-integration**: new capability.
  - **notion-integration**: ADDED exclusion of tasks owned by another integration.
  - **web-frontend**: ADDED VolunHub connection UI, project merge UI, and source indication.
- **Affected code:**
  - `integrations/volunhub/` (new) plus its migration.
  - `organizer/settings.py`: app registration, `VOLUNHUB_*` settings, and a beat entry.
  - `organizer/urls.py`: `/api/integrations/volunhub/…` and the browser callback
    `/integrations/volunhub/callback/`. The latter is already excluded from the service worker by the
    `/integrations/**` rule.
  - `integrations/notion/sync.py`: the push skips VolunHub-linked tasks.
  - `tasks/api/serializers.py` and `tasks/views.py`: a `volunhub` field via a soft
    `getattr(task, "volunhub_link")` lookup, plus a `select_related`.
  - `frontend/src/app/integrations/`: VolunHub service, model and settings card. Task list and detail
    templates get the badges.
  - `.env.example`, `docs/volunhub.md`, `CLAUDE.md`, `README.md`.
- **No new dependencies**: `httpx` and `cryptography` are already direct dependencies.
- **New per-user data:** encrypted third-party OAuth tokens (deleted on disconnect) and per-task
  sync snapshots.
- **Side effect in VolunHub:** every write Organizer pushes is attributed to the user and notifies
  the task's VolunHub watchers, as an edit made in VolunHub would. Only changed fields are sent.
- **Relies on VolunHub behaviour its own docs don't promise.** VolunHub's
  `docs/task-aggregator-api.md` says `/status/` is the only write, but its confinement middleware
  currently allows `PATCH` on tasks. Content write-back depends on that, and is designed to turn
  itself off cleanly if VolunHub later refuses it (see design D6).
