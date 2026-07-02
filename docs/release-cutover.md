# Release cutover: 2017 production → modernized app (no data loss)

Production currently runs the 2017 `organize` app against a database with the legacy `organize_*`
schema. The new code uses the `tasks_*` schema. **The data does not move by itself** — `manage.py
migrate` only *creates empty* `tasks_*` tables; [`migrate_legacy`](../tasks/management/commands/migrate_legacy.py)
is the one-time step that copies the rows across (see [data-migration.md](data-migration.md)).

Do the first cutover **by hand using the blue/green flow below** — not via the auto-deploy
workflow. The workflow's automatic `migrate` is correct for *ongoing* schema changes afterwards, but
it does not (and should not) run the data copy.

## Golden rule

**Migrate into a NEW, separate database and flip to it. Never run the data migration in place on the
live DB.** The live DB and old code stay untouched, so rollback is instant and nothing can be lost.

## Cutover checklist

### 1. Freeze writes
Stop the old app (or put it in maintenance) so no new data is created during the migration window.
For a single-user organizer this is seconds of "don't touch it", but it must happen **before** the
dump so the dump is the source of truth.

### 2. Take a fresh dump (this is your rollback point)
```bash
pg_dump -Fc -h <host> -p <port> -U <user> -d <legacy_db> -f organizer_cutover.dump
```
Keep this file safe. Everything below is reproducible from it.

### 3. Create a new empty database
```bash
createdb -h <host> -U <user> organizer_new
```
Leave the old database completely alone.

### 4. Point the new app at the new DB
In the new deployment's `.env`: `DB_NAME=organizer_new` (plus the other `DB_*`, `SECRET_KEY`,
`ALLOWED_HOSTS`, `CORS_ALLOWED_ORIGINS`).

### 5. Build the schema, then copy the data
```bash
uv run python manage.py migrate            # creates empty tasks_* in organizer_new
uv run python manage.py migrate_legacy organizer_cutover.dump
```
`migrate_legacy` restores the legacy tables from the dump, copies them into `tasks_*`
(defaulting `for_today=false`), re-syncs id sequences, imports the users/groups/API tokens, and
drops the temporary tables. It refuses to run if `tasks_taskitem` already has rows (use `--force`
only if you mean it).

### 6. Verify before flipping
```sql
SELECT count(*) FROM tasks_taskitem;        -- must match the source
SELECT count(*) FROM tasks_taskitem_tags;
SELECT count(*) FROM tasks_taskitem_tags tt -- orphan check, must be 0
  LEFT JOIN tasks_taskitem t ON tt.taskitem_id=t.id
  LEFT JOIN tasks_tag g ON tt.tag_id=g.id WHERE t.id IS NULL OR g.id IS NULL;
```
Then smoke-test the live API and log into the SPA:
```bash
uv run python manage.py runserver
curl -s -H "Authorization: Token <key from authtoken_token>" http://127.0.0.1:8000/api/task/ | head
```
Compare counts against the OLD app/DB. Only proceed when they match.

### 7. Flip traffic
Point the web server / process manager at the new app, and publish the new SPA bundle to the web
root. From here on, ongoing deploys use the GitHub Actions workflows
([deployment.md](deployment.md)) — their auto-`migrate` is now a no-op on the already-migrated DB.

### 8. Keep the old DB + old code for a rollback window
Don't delete anything for a week or two. If something is wrong, flip back: point the old code at the
untouched legacy DB. Because you never mutated it, rollback is immediate and lossless.

## Gotchas that actually bite

- **Don't let the deploy workflow do the first migration.** A bare `migrate` on the legacy DB makes
  empty `tasks_*` tables and the app looks empty — the data is still in `organize_*`. Always do the
  blue/green data copy first.
- **Dump *after* freezing writes**, or rows created between the dump and the freeze are lost.
- **Permissions / content types are intentionally not migrated** (`migrate_legacy` skips them — ids
  don't line up across schemas). The single superuser in the current dump is unaffected; if you've
  since added users with specific per-object permissions, re-grant them in the admin after cutover.
- **API tokens carry over** (the `authtoken_token` row is imported), so existing API clients keep
  working. Browser **sessions do not** — users just log in again.
- **Scoutfile SSO** needs `keys/scoutfile-2023.pem` on the server (gitignored). Token login works
  without it; only JWT/SSO login needs it.
- **Frontend origin**: the prod build uses same-origin (`apiBase: ''`). If the SPA is served from a
  different host than the API, set `apiBase` and add that origin to `CORS_ALLOWED_ORIGINS`.

## If you must migrate in place (not recommended)
The DB already contains `organize_*`, so the dump-restore steps in `migrate_legacy` would collide.
Prefer blue/green. If in-place is truly required, back up first, run `migrate`, then copy with a
variant that skips the `pg_restore` steps and only does the `INSERT … SELECT` + resequence against
the already-present `organize_*` tables — ask and I'll add a `--from-current-db` mode to the command.
