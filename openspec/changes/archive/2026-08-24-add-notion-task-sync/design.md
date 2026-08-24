# Design: Two-way Notion task sync

## Context
Organizer becomes an OAuth 2.0 **client** of Notion. It already implements the *server* side of the same
protocol family for `/mcp` (django-oauth-toolkit: authorization code + PKCE, dynamic registration,
discovery metadata), so the vocabulary is familiar — but Notion diverges from that setup in almost every
detail, and those divergences drive the design:

| | Organizer's `/mcp` server | **Notion (this change)** |
| --- | --- | --- |
| Client registration | we *serve* RFC 7591 DCR | **none — hand-registered once in Notion's dev settings** |
| Client type | — | **confidential; HTTP Basic at the token endpoint** |
| PKCE | we require S256 | **undocumented for this flow — not relied on** |
| Refresh token | we rotate | **rotates; no `expires_in` is returned** |
| Schema | ours | **ours — the database is created empty by us** |
| Change feed | — | **minute-rounded `last_edited_time` polling** |

The decisive difference from a Google Tasks or VolunHub sync is the last two rows. We are not squeezing
Organizer into someone else's data model; we **author** the Notion schema, so field fidelity is nearly
total. The hard problems are therefore not "what can we represent" but "how do we avoid fighting
ourselves" — echo suppression, coarse timestamps, and immovable page parents.

Verified Notion constraints that shape everything below:
- **`last_edited_time` is rounded *down* to the nearest minute** on pages, databases and blocks
  ([changelog](https://developers.notion.com/changelog/last-edited-time-is-now-rounded-to-the-nearest-minute)).
  Two edits in the same minute are indistinguishable by timestamp.
- **A page's `parent` cannot be changed.** `PATCH /v1/pages/{id}` explicitly cannot re-parent a page.
- **API version `2025-09-03` split databases into databases + data sources.** Row operations moved to
  `POST /v1/data_sources/{id}/query`, `GET|PATCH /v1/data_sources/{id}`; a page's parent is now
  `{"type": "data_source_id", …}`. A database id is **not** accepted where a data source id is required.
- **Query returns non-archived rows only**; `is_archived: true` returns archived ones. `in_trash` is
  **not** a queryable filter. Up to 10,000 results per query, paged on `next_cursor`.
- **Rate limit ≈ 3 requests/second average per connection**, plus a per-workspace limit; `429` carries
  `Retry-After`.
- **Size limits**: 2000 characters per rich-text object, 100 options per multi-select, 100 relation
  targets, 500 KB per request.
- `created_by` / `last_edited_by` / `created_time` / `last_edited_time` / `formula` / `rollup` /
  `unique_id` are **read-only** property types — readable, never writable.
- Notion's OAuth consent screen is a **page picker**: the user chooses which pages the integration may
  touch. We cannot reach anything they did not select.

## Goals / Non-goals
- **Goals:** per-user linking; a self-provisioned, Organizer-owned Notion database that starts empty;
  high-fidelity two-way sync of every field Organizer has; no sync ping-pong; no silent data loss.
- **Non-goals:** webhooks (see Decision 8); adopting a pre-existing Notion database; syncing task
  comments; syncing Projects/Tags as their own Notion databases; managing the Notion page **body**;
  a provider-agnostic integration framework.

## Decision 1 — Registration is manual, and PKCE is not relied on
Notion publishes no `registration_endpoint`; a **public integration** is created once by hand in Notion's
developer settings, yielding `NOTION_CLIENT_ID` / `NOTION_CLIENT_SECRET`. The authorize URL is
`https://api.notion.com/v1/oauth/authorize?client_id=…&response_type=code&owner=user&redirect_uri=…&state=…`;
`owner=user` is required. The code is exchanged at `POST https://api.notion.com/v1/oauth/token` with
**HTTP Basic** auth (`base64(client_id:client_secret)`) — not `client_secret_post`.

Notion's public-integration authorization guide documents no PKCE parameters (its separate MCP client
flow does accept `code_challenge` / `code_challenge_method=S256`). We therefore **do not rely on PKCE**:
`state` carries the CSRF burden alone. A `code_challenge` may be sent as defense-in-depth, but nothing in
the design depends on the authorization server enforcing it — and because Organizer is a *confidential*
client holding a real secret, PKCE buys comparatively little here.

**Redirect URI must match exactly.** Registered: `https://<prod-host>/integrations/notion/callback/`
and `http://localhost:8000/integrations/notion/callback/`.

### Token lifetime is undocumented — treat expiry as unknown
The token response contains `access_token`, `refresh_token`, `bot_id`, `workspace_id`, `workspace_name`,
`workspace_icon`, `owner` and `duplicated_template_id` — but **no `expires_in`**. Notion's tokens were
historically non-expiring; in practice they now expire on an undisclosed schedule, which is exactly why
Notion added refresh tokens. So the client must not compute expiry: it **refreshes reactively on `401`**,
persisting the rotated `refresh_token` from every refresh response. A refresh that returns
`invalid_grant` is terminal — flip the connection to `needs_reauth` and surface it in the UI.

Storing a connection without a `refresh_token` is allowed here (unlike the Google design, where it is a
hard error), because a Notion access token may legitimately be long-lived; but the absence is recorded
so the UI can warn that re-authorization will eventually be manual.

## Decision 2 — Who the callback belongs to
The SPA authenticates with a DRF `Authorization: Token` header, not a session cookie, so the browser
navigation Notion redirects back to carries no identity. Identity is bound into the OAuth `state`,
server-side:

1. SPA calls `POST /api/integrations/notion/connect/` (DRF-authenticated).
2. Server generates a random `state` (≥32 bytes), persists a short-lived single-use
   `NotionOAuthFlow{state, user, created_at}`, and returns the authorize URL.
3. SPA navigates the browser to Notion. The user consents **and picks the pages to share**.
4. The **callback view** (plain Django, unauthenticated) resolves the flow by `state` — rejecting
   unknown, expired (>10 min) or already-consumed states — exchanges the code, stores the tokens against
   `flow.user`, and redirects into the SPA.

With PKCE not relied upon, `state` being unguessable, single-use and short-lived is the *only* thing
standing between an attacker and a code injection. It is load-bearing and tested directly.

## Decision 3 — Provisioning: one database, created empty, owned by us
After connecting, the user picks a parent page (listed via `POST /v1/search` filtered to pages, which
returns exactly what they shared during consent). Organizer then calls `POST /v1/databases` with
`parent: {type: "page_id", page_id}` and an `initial_data_source.properties` schema, and stores both the
returned `database_id` **and** its `data_source_id` — the latter is what every subsequent row call needs.

Provisioning creates the **database only, no views**. Notion users have firm opinions about how their
databases are presented, and any view we created would become a thing the sync has to avoid clobbering
later. The schema is ours; the presentation is theirs.

**One database, not several.** This is forced by "**a page's parent cannot be changed**": if projects
were separate databases, moving a task between projects would mean deleting and re-creating its page,
churning its URL, its comments and its block content. With a single data source, a project change is an
ordinary property update. The same constraint rules out per-status or per-project databases entirely.

### The schema

| Organizer | Notion property | Type | Notes |
| --- | --- | --- | --- |
| `title` | `Name` | `title` | required — every data source needs exactly one |
| `description` | `Description` | `rich_text` | chunked into ≤2000-char text objects |
| `status` | `Status` | `select` | `idea` / `blocked` / `inprogress` / `givenup` |
| `completed` | `Done` | `checkbox` | |
| `completed_date` | `Completed at` | `date` | |
| `priority` | `Priority` | `select` | High / Normal / Low |
| `start_date` | `Start` | `date` | |
| `end_date` | `Deadline` | `date` | |
| `estimated_time` | `Estimate (min)` | `number` | |
| `for_today` | `Today` | `checkbox` | |
| `tags` | `Tags` | `multi_select` | |
| `project` | `Project` | `select` | |
| `parent_task` | `Parent task` | `relation` | self-relation, `single_property` |
| — | `Last edited by` | `last_edited_by` | read-only; powers echo suppression |

**Why `select` + `checkbox` rather than Notion's `status` type.** Notion's `status` type is prettier in
board views, but it is one field, and Organizer has two independent ones (`status` *and* `completed` — a
task can be `blocked` and completed, or `inprogress` and not). Collapsing them would be lossy in a way
we would then have to un-collapse on every read. Two properties mirror the model exactly. It also avoids
`status`'s requirement that custom options be assigned to groups at creation time.

**Why two date properties rather than one range.** A Notion `date` can hold `start` + `end`, which looks
like a natural fit for Organizer's `start_date`/`end_date`. It is not: Organizer routinely has a deadline
with **no** start date, and a Notion date range cannot express an end without a start. Separate `Start`
and `Deadline` properties round-trip every combination.

**Why the page body is not synced.** `description` maps to a `rich_text` property, leaving the Notion
page **body** entirely untouched by the sync. The alternative — mirroring `description` into body blocks —
was rejected on three counts: it costs one extra API request *per page* against a 3 req/s budget; a
local edit winning a conflict would rewrite the body and destroy any Notion-side formatting, lists or
embeds; and it takes away the one place a Notion user naturally expects to write freely. Leaving the
body alone turns that into a documented feature: **the page body is your Notion-only scratch space, and
Organizer will never touch it.** The cost is that `description` is capped by the rich-text limits.

### Schema drift
Users can rename or delete properties in Notion. Properties are therefore resolved by the **property id**
recorded at provisioning time, not by name, so a rename is harmless. Before each sync the data source is
retrieved and the recorded ids are checked; a **missing** property puts the connection into
`schema_drift` and pauses syncing with a repair action in the UI, rather than silently dropping a field.

## Decision 4 — Data model
New app `integrations/notion/` (label `notion`).

- **`NotionOAuthFlow`** — pending auth: `state` (unique), `user` (FK), `created_at`. Single-use, 10-min TTL.
- **`NotionConnection`** — per user: `user` (OneToOne), `access_token` + `refresh_token` (both encrypted),
  `bot_id`, `workspace_id`, `workspace_name`, `workspace_icon`, `status`
  (`active` | `needs_reauth` | `schema_drift` | `unprovisioned`), `connected_at`, `last_synced_at`,
  `last_full_sync_at`, `last_error`.
- **`NotionDatabase`** — the provisioned target, OneToOne with the connection: `database_id`,
  `data_source_id`, `parent_page_id`, `property_ids` (JSON: logical name → Notion property id),
  `pull_watermark`, `bootstrap_state` (`pending` | `running` | `done`), `bootstrap_cursor`,
  `created_at`.
- **`NotionTaskLink`** — per task: `database` (FK), `task` (OneToOne → `tasks.TaskItem`, `null=True`,
  `on_delete=SET_NULL`), `notion_page_id`, `notion_last_edited_time`, `local_changed_at`,
  `last_synced_at`. Unique `(database, notion_page_id)`.

**Why `SET_NULL` on `task`** — it doubles as a tombstone. When a user deletes a mirrored task in
Organizer the row survives with `task = NULL`, which is exactly the signal the push phase needs to trash
the Notion page. Without it, deleting locally would lose the `notion_page_id` and the page would live on
in Notion forever. No separate tombstone model, no `post_delete` signal.

**`Project` and `Tag` have no owner** — they are global in this app, while `TaskItem` has an `owner`.
Every push-side query must therefore filter `owner=connection.user`; filtering by project alone would
push another user's tasks into this user's Notion workspace. This is the single most important scoping
rule in the change, and it is asserted in tests.

## Decision 5 — Echo suppression is the primary anti-ping-pong mechanism
Every Notion page reports `last_edited_by` — and our OAuth token gave us our own **`bot_id`**. So the
pull phase can ask the question every polling sync struggles with: *did a human do this, or did I?*

**Rule: a page whose `last_edited_by.id == connection.bot_id` is our own write and is skipped.**

That is far more robust than timestamp bookkeeping alone, which matters more here than elsewhere because
Notion's minute rounding makes timestamps blunt. The watermark pair is still maintained as a backstop:
- `remote_changed = page.last_edited_time > link.notion_last_edited_time`
- `local_changed  = task.changed_date > link.local_changed_at`

**Watermarks must be re-stamped after every write, on both sides.** `changed_date` is `auto_now`, so the
sync's own inbound write bumps it — and the next run would read that as a spurious local edit and push it
straight back. After applying inbound: re-read the task and set `local_changed_at = task.changed_date`,
`notion_last_edited_time = page.last_edited_time`. After pushing: set both from the write's response.
Getting this wrong produces an infinite sync loop that also burns the rate limit; it is tested directly.

A server-side `last_edited_by does_not_contain <bot_id>` filter would shrink the result set, but it is
**not** used as the primary mechanism: it would also hide a page a human edited *before* our bot last
touched it. Suppression is decided per page, after fetching.

## Decision 6 — Minute-rounded timestamps, and the same-minute tie
`last_edited_time` is rounded **down** to the minute. Three consequences, each handled explicitly:

1. **The incremental filter overlaps.** Pull filters on
   `last_edited_time on_or_after (pull_watermark − 120s)`. A 2-minute window (not the 60s a
   second-precision API would need) absorbs both the rounding and clock skew. Applies must therefore be
   **idempotent** — re-reading an already-applied page must be a no-op.
2. **Same-minute conflicts cannot be ordered.** When both sides changed and
   `page.last_edited_time` and `task.changed_date` fall in the **same minute**, the timestamps carry no
   information about who was last. The tie is broken **in Organizer's favour**: it is the source of
   truth and the finer-grained clock. Outside a tie, the more recent change wins. Every conflict outcome
   is logged.
3. **A change can hide inside the watermark.** An edit made in the same minute as the last successful
   pull may fall outside the next window. The 2-minute overlap covers this, and the periodic full
   reconciliation is the backstop.

## Decision 7 — Sync engine
Per connection, **pull then push** (so pages that arrive from Notion get local ids and links before the
push phase looks for unlinked local tasks).

**Bootstrap.** The database starts empty, so the first run is a pure upload of every task with
`owner=connection.user`. At ~3 requests/second and one `POST /v1/pages` per task, a few hundred tasks
takes minutes — far too long for a request/response cycle, and it must survive a worker restart. It runs
as a Celery task in `bootstrap_state=running`, walking tasks in `pk` order and advancing
`bootstrap_cursor` as it goes, so a retry resumes rather than duplicating. Incremental sync does not
start until `bootstrap_state=done`. Select/multi-select options (statuses, priorities, projects, tags)
are seeded onto the data source **before** the upload, mapping `Tag.color` (a hex string) to the nearest
colour in Notion's fixed palette.

**Pull** — `POST /v1/data_sources/{id}/query` with the overlapping `last_edited_time` filter, sorted
ascending, paged on `next_cursor`. For each page: `last_edited_by == bot_id` → **skip** (our own echo);
linked → **merge**; unlinked → **create locally** (owned by `connection.user`).

**Push** — in order:
1. `task IS NULL` links (locally deleted) → `PATCH {in_trash: true}`, drop the link.
2. Tasks with `owner=connection.user` and no link → `POST /v1/pages` with
   `parent: {type: "data_source_id", …}`, create the link.
3. Linked tasks with `changed_date > link.local_changed_at` → `PATCH /v1/pages/{id}`.

Relations are resolved after the fact: `parent_task` can only be written once the parent's own page
exists, so a task whose parent is not yet mirrored is pushed without the relation and patched in a second
pass at the end of the run.

**Full reconciliation** — every `NOTION_FULL_SYNC_HOURS` (default 24), an unfiltered query walks the
whole data source. This is the **only** way deletions made in Notion are detected: the query endpoint
returns non-archived rows only and cannot filter on `in_trash`, so a trashed page simply stops appearing.
Links whose page is missing from the full sweep are confirmed with `GET /v1/pages/{id}` — which still
returns a trashed page, flagged — and the mirrored local task is then deleted, symmetrically with the
local-delete → trash-upstream path. The sweep also repairs drift that the minute-granularity incremental
filter missed.

**Inbound merges are whole-field.** Because we own the schema, there is no "fields Notion cannot hold"
carve-out as there would be for a thinner provider — every property maps to exactly one local field. Two
local behaviours still need care:
- **`completed_date` is a `MonitorField(monitor="completed")`**, whose `pre_save` overwrites any assigned
  value with `now()` when `completed` flips to `True`. Importing a task completed yesterday would restamp
  it as completed just now. Fix: after `save()`, write the true timestamp with
  `TaskItem.objects.filter(pk=…).update(completed_date=…)`, which bypasses `pre_save` — and also bypasses
  `auto_now` on `changed_date`, so the correction does not masquerade as a fresh local edit.
- **`TaskItem.save()` copies the project's tags onto the task.** An inbound project change therefore adds
  tags locally; those flow back to Notion on the next push. Expected, but it means `Tags` in Notion is not
  purely user-controlled, and it is called out in the UI copy.

**Global `Project`/`Tag` are matched, never created.** An inbound `Project` or `Tags` value is resolved
against existing rows (by title / slug, case-insensitively). An unrecognised option is **ignored and
logged** — never auto-created. Projects and tags are global in this app, so honouring a typo in one
user's Notion workspace would pollute every user's list. Moving a task between *existing* projects from
Notion — the common case — works normally.

## Decision 8 — Webhooks are deliberately deferred
Notion does have webhooks (`page.created`, `page.properties_updated`, `page.content_updated`,
`page.deleted`, `page.undeleted`, `data_source.schema_updated`), and their payloads even carry an
`authors` array that would complement `bot_id` echo suppression. They are still out of scope:

- A subscription is created **in Notion's developer dashboard by hand**, and verified by copying a
  one-time `verification_token` out of the first delivery and pasting it back into Notion's UI. That is
  an operator ritual, not something the app can provision per user.
- Delivery is explicitly **at-most-once**, with events arriving **out of order**. A missed event is
  simply lost — so polling and full reconciliation are required for correctness *regardless*.

Webhooks would therefore only reduce latency, not replace any machinery. They slot in later behind a
signature-checked endpoint (HMAC-SHA256 of the body keyed by the `verification_token`) that nudges the
existing sync for one workspace — with no schema change. That is a clean separate change.

## Decision 9 — Execution model and rate limiting
The repo already runs Celery + beat for recurring-task generation, so this follows `tasks/tasks.py` +
`CELERY_BEAT_SCHEDULE` exactly:
- **Beat**: `integrations.notion.sync_notion` every `NOTION_SYNC_MINUTES` (default 10 — below that, the
  minute-rounded change feed gives diminishing returns), iterating active connections, each in its own
  transaction so one bad connection cannot abort the batch.
- **`manage.py sync_notion [--user <id>] [--full]`** — manual fallback when the broker is down,
  mirroring `generate_recurring_tasks`.
- **`POST /api/integrations/notion/sync/`** — authenticated "sync now", enqueues for the requesting user
  only (it does not run inline; bootstrap alone can exceed any sane request timeout).

HTTP via **`httpx`** (sync client — the WSGI request path stays sync). The client carries a
**token-bucket pacer at 3 requests/second** because Notion's limit is a documented average rather than a
hard burst ceiling, so pacing beats reacting. `429` honours `Retry-After`; `5xx`/`529` back off with
jittered exponential retry; `401` triggers one refresh-and-retry.

**Inbound writes broadcast for free.** `TaskItem` model signals already push `task.created` /
`task.updated` / `task.deleted` over Channels on `transaction.on_commit`, so tasks arriving from Notion
appear live in the user's open SPA tabs with no extra work in this change.

## Decision 10 — Token security
Tokens are live credentials to a third-party workspace, so they are **encrypted at rest** with Fernet
(`cryptography`), keyed by `INTEGRATIONS_TOKEN_KEY` (named generically so sibling integrations reuse it),
falling back to a key derived from `SECRET_KEY` in dev. Tokens are never logged and never returned to the
SPA — the SPA sees connection status, the workspace name/icon and the database URL. Disconnect deletes
the stored credentials and all link rows; Notion has no token revocation endpoint, so the UI also tells
the user to remove the connection from their Notion settings to fully revoke access.

## Module layout
```
integrations/
  __init__.py
  crypto.py              # Fernet encrypt/decrypt (shared by future integrations)
  notion/
    __init__.py
    apps.py              # AppConfig (label "notion")
    models.py            # NotionOAuthFlow, NotionConnection, NotionDatabase, NotionTaskLink
    oauth.py             # authorize-URL build, Basic-auth token exchange, rotating refresh
    client.py            # NotionClient: paced HTTP, search/create db/query/create/patch pages
    schema.py            # the property schema, provisioning, drift detection, option seeding
    mapping.py           # TaskItem <-> Notion property values, both directions
    sync.py              # bootstrap + pull/push engine (per connection)
    views.py             # DRF: connect/disconnect/status/pages/provision/sync ; plain callback view
    urls.py
    tasks.py             # Celery tasks
    management/commands/sync_notion.py
    tests/
```

## Risks / trade-offs
- **Minute-granularity change detection.** Rapid successive edits on both sides within one minute cannot
  be ordered; the Organizer-wins tiebreak is deterministic but arbitrary. Mitigated by echo suppression
  (most same-minute pairs are our own write) and the full sweep.
- **Notion-side deletion is only noticed on the full sweep** — up to `NOTION_FULL_SYNC_HOURS` late.
  The query API gives no cheaper signal; webhooks would fix the latency later.
- **Trashing on local delete is destructive but symmetric.** Notion's trash is recoverable for 30 days,
  which — at Notion's default 30-day trash retention — makes this safer than the equivalent Google
  Tasks behaviour. Still disclosed in the UI.
- **`description` is capped by rich-text limits** where the local field is unbounded. Long descriptions
  are chunked, and truncation (if Notion rejects an oversized value) is logged rather than silent.
- **Page body is never synced.** Framed as a feature, but a user who writes their task notes in the body
  and expects them in Organizer will be surprised — hence explicit UI copy.
- **Bootstrap is slow by construction.** ~3 tasks/second. A large account takes minutes; progress is
  surfaced in the UI so it does not look hung.
- **Schema drift pauses sync** rather than degrading. Chosen over silently dropping a field, but it does
  mean a user deleting a property in Notion stops their sync until they hit repair.
- **PKCE is not relied on.** It is undocumented for this flow, so `state` carries the full CSRF burden
  and its single-use/expiry handling must be exactly right.

## Resolved
Three questions were open when this proposal was drafted; all three were decided in favour of the
proposed default, and the decisions above reflect them:
- **Unrecognised `Project` / `Tags` values from Notion are ignored and logged**, never created
  (Decision 7). Both models are global here, so honouring a typo in one user's workspace would pollute
  every user's list.
- **Provisioning creates the database only** — no views (Decision 3). Presentation stays the user's.
- **Trashing a page in Notion deletes the mirrored task** (Decision 7). Symmetric with the reverse path,
  and the only option that does not need a "stop syncing this one" flag to avoid re-creating the page on
  the next push.

## Open questions
- Confirm during implementation that `last_edited_by.id` for integration-authored edits equals the
  `bot_id` returned by the OAuth exchange. The whole echo-suppression design rests on it; if it does not
  hold, the watermark pair becomes primary and the tests must pivot. This is a verification task, not a
  design choice — see task 11.6.
