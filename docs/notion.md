# Two-way Notion task sync

Organizer can mirror a user's tasks into a Notion database and keep both sides in step. Unlike a
typical integration, it does **not** adapt to a database you already have: it **creates its own,
empty**, and owns the schema. That is what makes the mapping near-total — priority, workflow status,
tags, project, start date, estimated time and parent/child all get a real column.

- Setup is per-deployment (one registered integration) plus per-user (each person connects their own
  workspace).
- Syncing runs on Celery beat; there is also a management command and a "Sync now" button.

---

## 1. Register the integration (once per deployment)

1. Go to <https://www.notion.so/my-integrations> and create a **public** integration.
   (A public integration is required: internal ones have no OAuth flow and are bound to one
   workspace.)
2. Under **Capabilities**, grant read *and* update/insert content.
3. Under **OAuth Domain & URIs**, add the redirect URI **exactly** as your deployment will send it —
   scheme, host, path and trailing slash all have to match:

   ```
   https://organizer.example.com/integrations/notion/callback/
   http://localhost:8000/integrations/notion/callback/     # for local development
   ```

4. Copy the **OAuth client ID** and **client secret**.

Notion has no dynamic client registration, so this step cannot be automated.

## 2. Configure the server

Add to `.env` (see `.env.example`):

```bash
NOTION_CLIENT_ID=...
NOTION_CLIENT_SECRET=...
NOTION_REDIRECT_URI=https://organizer.example.com/integrations/notion/callback/

# Pinned API version. 2025-09-03 is the release that split databases into databases + data
# sources; the sync addresses data sources directly and will not work on older versions.
NOTION_API_VERSION=2025-09-03

# Incremental sync cadence, and how often a run escalates to a full reconciliation.
NOTION_SYNC_MINUTES=10
NOTION_FULL_SYNC_HOURS=24

# Where the SPA lives — the OAuth callback redirects the browser back here.
FRONTEND_BASE_URL=https://organizer.example.com

# Fernet key encrypting stored OAuth credentials. Shared by all integrations.
INTEGRATIONS_TOKEN_KEY=...
```

Generate the token key with:

```bash
python -c 'from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())'
```

> **Set `INTEGRATIONS_TOKEN_KEY` in production.** Left blank, a key is derived from `SECRET_KEY` —
> convenient for development, but it means rotating `SECRET_KEY` silently strands every stored
> token and every user has to reconnect.

Then apply migrations and make sure Celery beat is running (it is what drives periodic syncing):

```bash
uv run python manage.py migrate
uv run celery -A organizer worker -B
```

## 3. Connect an account (per user)

1. In the app, go to **Integrations** in the sidebar and click **Connect Notion**.
2. On Notion's consent screen, **select the pages to share**. This matters: the integration can only
   see — and only create its database under — pages ticked here. Sharing a single dedicated parent
   page is plenty.
3. Back in the app, pick that page and click **Create database**. Organizer creates an empty
   *Organizer tasks* database under it and starts uploading existing tasks.

The upload is paced to Notion's rate limit (~3 requests/second), so a few hundred tasks takes a few
minutes. Progress is shown on the Integrations screen, and it resumes safely if a worker restarts.

## 4. Running syncs manually

```bash
# Every connected user
uv run python manage.py sync_notion

# One user
uv run python manage.py sync_notion --user 3

# Force a full reconciliation (the only pass that notices pages trashed in Notion)
uv run python manage.py sync_notion --full
```

---

## What syncs, and what does not

| Organizer | Notion property | Notes |
| --- | --- | --- |
| title | `Name` (title) | |
| description | `Description` (rich text) | chunked; very long text is capped by Notion's limits |
| status | `Status` (select) | |
| completed | `Done` (checkbox) | separate from Status, because Organizer's two fields are independent |
| completed_date | `Completed at` (date) | |
| priority | `Priority` (select) | |
| start_date | `Start` (date) | |
| end_date | `Deadline` (date) | |
| estimated_time | `Estimate (min)` (number) | |
| for_today | `Today` (checkbox) | |
| tags | `Tags` (multi-select) | matched against existing tags, never created |
| project | `Project` (select) | matched against existing projects, never created |
| parent_task | `Parent task` (relation) | self-relation within the same data source |

**The Notion page body is never touched.** Notes you write in the body of a task page stay in
Notion — deliberately, so you have somewhere to write freely that the sync will not overwrite.

**Projects and tags are matched, not created.** Both are global in this app (neither model has an
owner), so a value invented in one person's Notion workspace would appear for everyone. Unknown
values are ignored and logged; moving a task between *existing* projects from Notion works normally.

**Deletion is symmetric.** Deleting a task in Organizer moves its Notion page to the trash;
trashing a page in Notion deletes the task in Organizer. Notion's trash is recoverable for 30 days
by default. Note that Notion-side deletions are only noticed on a **full reconciliation** (default
every 24h), because Notion's query API returns only non-archived rows and cannot be asked about
trashed ones.

## Behaviours worth knowing

- **Notion records edit times only to the nearest minute.** If both sides change a task within the
  same minute, the timestamps cannot order them and **Organizer wins**. Outside that, the more
  recent change wins.
- **The sync recognises its own writes.** Every Notion page records who edited it last, and the
  OAuth exchange gives us our own bot id, so the sync skips pages it wrote itself instead of
  looping them back.
- **Renaming a property in Notion is fine.** Properties are addressed by id. *Deleting* one pauses
  the sync with a "schema changed" warning rather than silently dropping that field — restore the
  property and hit retry.
- **Deadline times survive.** If you set a deadline of 14:30 in Organizer and edit the date (but not
  the time) in Notion, the 14:30 is preserved; Notion simply cannot show it.

## Troubleshooting

**"Reconnect needed."** Notion rejected the stored credentials. Notion rotates refresh tokens and
does not publish an access-token lifetime, so the sync refreshes reactively; when a refresh is
refused outright the connection pauses and asks the user to reconnect.

**"You have not shared any pages."** The user did not tick any page on the consent screen. In
Notion, open the target page → **… → Connections** → add Organizer, then click *Check again*.

**"The Notion database changed."** A required property was deleted. Re-add it in Notion (any name —
matching is by id, so only deletion breaks it) and retry, or disconnect and re-provision.

**Nothing is syncing.** Check that Celery beat is running; `manage.py sync_notion` is the fallback.

**Disconnecting.** Removing the connection here deletes the stored credentials. Notion exposes no
token-revocation endpoint, so users should also remove Organizer in Notion under
**Settings → Connections**.

## Not implemented

**Webhooks.** Notion does have them, but a subscription is created and verified by hand in Notion's
developer dashboard, and delivery is explicitly *at-most-once* with out-of-order events — so polling
and full reconciliation would still be required for correctness. Webhooks would only reduce latency,
and can be added later without a schema change.

Also out of scope: syncing task comments to Notion comments, adopting a pre-existing Notion
database, and syncing projects or tags as their own Notion databases.
