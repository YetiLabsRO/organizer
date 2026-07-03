# Change: Add task statistics / analytics

## Why
The app captures rich per-task data (tags, completion timestamps, status, priority) but offers no
way to see patterns across tasks — how work is distributed over tags, how many tasks get solved per
day/week, or how throughput trends over time. Users want an analytics view, wired to the same
filters as the task list, to understand their own productivity.

## What Changes
- **Backend**: add a read-only `GET /api/task/stats/` action on the task ViewSet that reuses the
  existing `TaskFilterSet` (so it honours the exact same filters as `GET /api/task/`) and returns a
  single aggregated payload:
  - `tag_distribution` — task count per tag over the filtered set (a multi-tag task counts once per
    tag), including an untagged bucket.
  - `solved_timeline` — completed tasks bucketed by day or week (`?bucket=day|week`) on
    `completed_date`, counted once per task.
  - `solved_by_tag_timeline` — the same buckets split per tag (data for the cumulative stacked-area
    chart).
  - `created_vs_completed_timeline` — created and completed counts per bucket (burn-up data).
  - `status_breakdown` / `priority_breakdown` — counts per status and per priority.
  - `calendar_heatmap` — solved-per-day counts (GitHub-style heatmap data).
  - `time_to_completion_by_tag` — average `completed_date − created_date` per tag.
- **Frontend**: add a new standalone `/tasks/stats` page (Angular signals, `OnPush`) that inherits
  the task list's filters via URL query params, exposes its own filter bar + a day/week toggle, and
  renders the visualizations with **Chart.js** (added as a dependency, used directly with no Angular
  wrapper). A calendar heatmap is rendered as a lightweight CSS-grid component (no extra library).
  A "Stats" link is added to the task list, carrying the current filters.

## Impact
- Affected specs: **task-statistics** (new capability — the stats API), **web-frontend** (new stats
  page).
- Affected code:
  - Backend: `tasks/views.py` (new `@action`), a new `tasks/api/stats.py` (aggregation helpers) or
    inline, tests under `tasks/tests/`. Reuses `tasks/filters.py` unchanged.
  - Frontend: `frontend/package.json` (add `chart.js`), `frontend/src/app/app.routes.ts`, a new
    `frontend/src/app/tasks/task-stats/` component tree, a small reusable Chart.js canvas wrapper,
    a `CalendarHeatmap` component, a `TaskStatsService`, and reuse of `TaskFilters`.
- New dependency: `chart.js` (frontend only). No backend dependencies added.
