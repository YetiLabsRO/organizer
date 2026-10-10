# Two-way VolunHub task sync

Organizer can bring the tasks **assigned to you** in [VolunHub](https://volunhub.scout.ro) into your
task lists and keep both sides in step: edit a title or complete a task here and VolunHub follows;
change it there and Organizer follows. Organizer **never creates or deletes** anything in VolunHub —
it only updates tasks that already exist there.

- No per-deployment registration by hand: Organizer registers itself with VolunHub the first time
  anyone connects.
- Each user connects their own VolunHub account from **Integrations** in the sidebar.
- Syncing runs on Celery beat; there is also a management command and a "Sync now" button.

---

## 1. Configure the server

Add to `.env` (see `.env.example`):

```bash
VOLUNHUB_BASE_URL=https://volunhub.scout.ro
# VOLUNHUB_REDIRECT_URI=...    # defaults to <MCP_BASE_URL>/integrations/volunhub/callback/
VOLUNHUB_SYNC_MINUTES=10
FRONTEND_BASE_URL=https://organizer.example.com
INTEGRATIONS_TOKEN_KEY=...      # shared with Notion; encrypts stored tokens
# VOLUNHUB_CLIENT_ID=...        # optional: use a client registered out of band instead
```

- `VOLUNHUB_REDIRECT_URI` is declared to VolunHub when Organizer registers, and VolunHub matches it
  byte for byte. It must be the **public** URL of this deployment's callback. It defaults to
  `<MCP_BASE_URL>/integrations/volunhub/callback/`, and outside `DEBUG` a `localhost` value is refused
  at connect time rather than registered. Changing it later makes
  the next connect register a new client; existing connections keep working.
- `VOLUNHUB_BASE_URL` must be `https` outside `DEBUG`. Leave it empty to disable the integration.
- Run `migrate`, and make sure a Celery **worker and beat** are running (`sync-volunhub` is in
  `CELERY_BEAT_SCHEDULE`).
- **nginx:** the callback is a plain browser navigation, so `/integrations/` must reach Django rather
  than the SPA. The `location /integrations/` block documented in the README (added for Notion)
  already covers it. Check with
  `curl -sI https://organizer.example.com/integrations/volunhub/callback/` — a `302` means Django
  answered; a `200` with `<app-root>` means the SPA swallowed it.

## 2. How the connection works

1. **Register (once).** On the first connect Organizer `POST`s to VolunHub's `/register` (RFC 7591)
   as a **public** client (`token_endpoint_auth_method: "none"`) asking for exactly
   `mcp:tasks:read mcp:tasks:write`. That exact scope set is what confines the client to VolunHub's
   tasks and projects endpoints; anything broader would be a full-scope client. So if VolunHub hands
   back any other scope, Organizer **refuses to store the client** and the connect fails.
2. **Authorize.** The user is sent to VolunHub's `/authorize` with PKCE (S256) and a single-use
   `state` bound to them. VolunHub shows its consent screen every time.
3. **Callback.** `/integrations/volunhub/callback/` exchanges the code (no client secret — the PKCE
   verifier proves it), stores the tokens encrypted, and queues a first sync.
   - Unticked "read your tasks and projects" → nothing is stored.
   - Unticked "change your tasks" → the connection is **read-only**: VolunHub changes come in,
     nothing goes out. Reconnect to fix.
4. **Tokens.** Access tokens last ~1 h and are refreshed shortly before expiry (and on any `401`).
   Refresh tokens rotate on every use with no grace period, so refreshes for one user are serialized
   — two workers refreshing at once would otherwise look like a revoked grant. A refused refresh marks
   the connection **needs re-authorization**; the Integrations screen offers a reconnect.

The client only ever calls `/api/v1/projects/tasks…` and `/api/v1/projects/projects…`; anything else
is refused before a request is sent.

## 3. What syncs

Only tasks **personally assigned** to you come in. Tasks you only reported or watch, and tasks
assigned only to a team you belong to, do not. Finished tasks are imported too (as completed, with
their last VolunHub change as the completion date).

Imported tasks keep VolunHub's **created** and **last changed** dates, so they sit in the task list
(newest change first) and in the statistics where they belong rather than in one block dated to the
import. Tasks imported before this was the case are corrected on the next sync; one you have edited
here since keeps its newer "last changed" date.

| Organizer | VolunHub | Notes |
| --- | --- | --- |
| Title | `title` | |
| Description | `description` | Markdown both sides |
| Start date | `start_date` | |
| Deadline (`end_date`) | `deadline` | VolunHub's `end_date` (end of the work window) is not used |
| Estimate | `estimated_time` | minutes both sides |
| Priority low / normal / high | `priority` 1 / 2 / 3 | |
| Status + completed | workflow state | see below |
| Project | task's project | **import-only**, see §5 |

Not synced: tags, sub-tasks, "for today", order (Organizer-only); kind, actual time, assignees,
teams, watchers, comments (VolunHub-only).

### Status

| VolunHub state | Organizer |
| --- | --- |
| Ciornă (draft), Planificat (planned) | Idea |
| În lucru (in progress) | In progress |
| Blocat (blocked) | Blocked |
| Finalizat (finished) | Completed (status left as it was) |

Going the other way, completing a task sends *finished*; Idea / In progress / Blocked send
*planned* / *in progress* / *blocked*. VolunHub's workflow has no direct path from *draft* or
*finished* to *in progress*, so Organizer goes through *planned* first (two calls). **"Given up"
has no VolunHub equivalent: it is never sent, and never overwritten by VolunHub.** A task with no
workflow in VolunHub (some tasks created by other VolunHub modules) has its status left alone.

## 4. How changes flow — and conflicts

VolunHub does not record when a task's status changed, its `completed` column is not kept up to
date, and it offers no "changed since" query. So every sync reads your **full** assigned-task list
and compares **values**, field by field, against a snapshot of what both sides last agreed on:

- changed only in VolunHub → applied here;
- changed only here → sent to VolunHub (only the changed fields);
- changed on both sides to **different** values → **Organizer's value wins** and is sent to VolunHub.

Because whatever Organizer sends becomes the new snapshot, its own writes are never read back as
changes. Every change Organizer sends **notifies that task's watchers in VolunHub**, just as an edit
made in VolunHub would.

**If VolunHub refuses content edits.** VolunHub's own docs describe this token as status-only, though
it currently accepts edits to title, description, dates, estimate and priority. If it ever answers
`403` to such an edit, Organizer switches that connection to **status-only**: content then only
flows from VolunHub to Organizer, status still goes both ways, and the Integrations screen shows a
banner with a **Retry content sync** button.

An unreachable status change (`409`) or a rejected edit (`400`) is recorded on that task ("Sync
problem" badge) and retried on the next sync; the rest of the run carries on.

## 5. Projects

The first time a task from a VolunHub project arrives, Organizer creates a project with the same name
and puts the task in it. Projects are shared by everyone on an Organizer server, so this project is
visible to other users too.

If you already had a matching project, use the **Projects** table on the Integrations screen to
**merge**: pick your project for that VolunHub project, and

- every task in the auto-created project moves to yours, and the auto-created project is deleted;
- future tasks from that VolunHub project land in yours;
- your project is never renamed by the sync (an auto-created one follows renames in VolunHub).

Picking a different project again later moves only the tasks that came from that VolunHub project.
Moving a task to another project **here** is kept and never sent to VolunHub (VolunHub's API cannot
move tasks between projects); moving it **in VolunHub** is applied here. Deleting an auto-created
project here does not bring it back: its tasks arrive without a project until you merge.

## 6. Removals and deletions

- **Unassigned from you, or deleted, in VolunHub** → the task **stays here**, marked "Removed from
  VolunHub (unassigned / deleted)", and is no longer synced. Organizer tells the two apart by
  looking the task up; if that lookup fails it simply checks again next time.
- **Reassigned to you again** → the same local task is re-attached and syncing resumes. No duplicate.
- **Deleted here** → nothing happens in VolunHub; the task is not imported again while it remains
  assigned to you.
- **Disconnect** → Organizer revokes its access in VolunHub and deletes the stored credentials. Your
  imported tasks stay, marked "VolunHub disconnected". Reconnecting re-attaches them.

## 7. Notion

Tasks that came from VolunHub — including ones since removed from VolunHub — are **not** mirrored to
Notion, so each task has a single external owner and the two syncs can never fight over it.

## 8. Running it by hand

```bash
uv run python manage.py sync_volunhub              # every connected user
uv run python manage.py sync_volunhub --user 3     # one user
```

Only one sync per user runs at a time; an overlapping run (e.g. "Sync now" during a scheduled run)
is skipped rather than doubled.

## 9. Troubleshooting

| Symptom | Cause / fix |
| --- | --- |
| Connect says registration failed | VolunHub unreachable, or it returned a broader scope than requested (the client is refused on purpose). Check `VOLUNHUB_BASE_URL`. |
| Blank page after approving in VolunHub | The SPA swallowed the callback — see the nginx check in §1. |
| VolunHub sends you to `localhost` after approving | The client was registered with a local redirect URI. Set `MCP_BASE_URL` (or `VOLUNHUB_REDIRECT_URI`) to the public URL and restart; the next connect registers a new client automatically. |
| "Reconnect needed" | The refresh token was revoked or expired (30 days unused). Reconnect. |
| "Read-only" | The change permission was unticked at consent. Reconnect and keep both ticked. |
| "Only status changes are sent" | VolunHub refused a content edit (§4). Retry from the banner once VolunHub allows it again. |
| A task never leaves "in progress" in VolunHub | Look for its "Sync problem" badge — VolunHub refused the transition (`409`). |
| A task is missing | Only tasks assigned to you personally are imported (not team assignments). |
