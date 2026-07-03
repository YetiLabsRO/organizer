## 1. Backend — stats endpoint
- [x] 1.1 Add aggregation helpers (in `tasks/api/stats.py`) that take a filtered `TaskItem` queryset
      and a `bucket` and return each section: tag distribution, solved timeline, per-tag solved
      timeline, created-vs-completed timeline, status/priority breakdown, calendar heatmap,
      time-to-completion per tag.
- [x] 1.2 Add `@action(detail=False, methods=["get"], url_path="stats")` `stats` to
      `TaskItemViewSet` that derives the filtered id set via `self.filter_queryset(...)`, builds a
      clean base queryset, reads `?bucket=day|week` (default `day`, reject others), and returns the
      composite payload.
- [x] 1.3 Ensure time-based sections restrict to `completed=True, completed_date__isnull=False`, and
      that per-tag sections count per tag while total timelines count each task once. Include an
      untagged bucket in the distribution.
- [x] 1.4 Truncate on `completed_date`/`created_date` in the active timezone; emit ISO dates.

## 2. Backend — tests
- [x] 2.1 Auth + ownership: unauthenticated request rejected; only the caller's tasks are aggregated.
- [x] 2.2 Filters honoured: `?tags=`, `?contains=`, `?completed=` change the aggregates the same way
      they change `GET /api/task/`.
- [x] 2.3 Bucketing: day vs week grouping of `solved_timeline`; invalid `bucket` rejected.
- [x] 2.4 Semantics: multi-tag task counted once in `solved_timeline` but in each per-tag series;
      untagged bucket present; time-based sections ignore not-completed tasks.
- [x] 2.5 `time_to_completion_by_tag` averages `completed_date − created_date` correctly.

## 3. Frontend — plumbing
- [x] 3.1 Add `chart.js` to `frontend/package.json` and install.
- [x] 3.2 Add `TaskStatsService.getStats(filters: TaskFilters, bucket)` calling
      `GET /api/task/stats/` with the serialised filters + bucket.
- [x] 3.3 Add lazy route `tasks/stats` before the catch-all (`loadComponent`, so Chart.js stays out
      of the initial bundle); add a "Stats" link in the task list toolbar that navigates carrying the
      current `TaskFilters` as query params (plus a top-nav Stats link).

## 4. Frontend — components
- [x] 4.1 `ChartCanvasComponent` (standalone, OnPush): input = Chart.js config; create in `effect()`,
      update on change, destroy on teardown.
- [x] 4.2 `CalendarHeatmapComponent` (standalone, OnPush): CSS-grid of day cells shaded by count.
- [x] 4.3 `TaskStatsComponent` (standalone, OnPush, signals): parse query params → `TaskFilters`;
      filter bar (tags, search, completed/todo, day/week toggle) writing back to the URL; fetch
      stats; compute cumulative sums client-side.
- [x] 4.4 Render charts: tag distribution (horizontal bar, per-tag colors), solved per day/week
      (bar + toggle), cumulative stacked area per tag, burn-up (created vs completed),
      status + priority breakdown (doughnut), time-to-completion per tag (horizontal bar), and the
      calendar heatmap. Show an empty state when there is no data and a note that multi-tag tasks
      count in each tag.

## 5. Validation
- [x] 5.1 `uv run python manage.py test` (backend, incl. new stats tests) and `uv run ruff check .`.
- [x] 5.2 `cd frontend && npm run build` (or `ng build`) succeeds with Chart.js wired in.
- [x] 5.3 Manual: navigate list → Stats with active filters; confirm charts reflect the same filtered
      set and the day/week toggle re-buckets.
