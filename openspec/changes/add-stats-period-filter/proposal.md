# Change: Add a period selector to the task statistics view

## Why
The stats dashboard shows all-time data only. Users want to focus it on a time window — today, the
last week, the last month, a custom range, or all time — to answer "what did I get done this period?"

## What Changes
- **Backend**: add `completed_after` and `completed_before` date filters (inclusive, on the local
  date of `completed_date`) to `TaskFilterSet`. Because the stats endpoint reuses `TaskFilterSet`,
  these bound the entire `/api/task/stats/` payload with no endpoint changes.
- **Frontend**: add a period selector to the `/tasks/stats` page — Today / Last week / Last month /
  All time presets plus a custom From–To range. The selection is stored in the URL as
  `completed_after`/`completed_before` (so it stays bookmarkable and drives the same filter contract),
  and the totals tiles adapt when a bounded period is active (a bounded period is a completions view,
  so it shows "completed in period" rather than the open-backlog tiles).

## Impact
- Affected specs: **task-statistics** (period range on the endpoint), **web-frontend** (period
  selector on the stats page).
- Affected code: `tasks/filters.py` (two filters + `Meta.fields`), `tasks/tests.py` (period tests),
  `frontend/src/app/tasks/task-filters.ts` (serialise the two params), and the stats page
  (`task-stats.component.*`).
- No new dependencies; "all time" preserves the existing all-time behavior (no bounds).
