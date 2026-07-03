## Context
The task list already builds a `TaskFilters` object that serialises to the query string understood by
`TaskFilterSet` (`tasks/filters.py`). Tasks carry a `completed` boolean and an auto-stamped
`completed_date` (`MonitorField`, set when `completed` flips to `True`, cleared on un-complete), plus
M2M `tags`, `status`, `priority`, and `created_date`. This gives every axis the analytics need
without schema changes. The stats view must honour the **same filters** as the list.

## Goals / Non-Goals
- Goals: one filtered, owner-scoped stats endpoint reusing `TaskFilterSet`; a `/tasks/stats` page
  that inherits the list filters and renders the requested charts + four extras; add exactly one
  frontend dependency (Chart.js).
- Non-Goals: no new persisted models or migrations; no cross-user/aggregate-across-users analytics;
  no server-side chart rendering; no caching layer (dataset is per-user and small).

## Decisions

### Backend: one `@action(detail=False, url_path="stats")` on `TaskItemViewSet`
Within the action, derive the filtered set exactly as the list does:
```python
qs = self.filter_queryset(self.get_queryset())        # owner-scoped + TaskFilterSet
ids = list(qs.values_list("id", flat=True).distinct()) # collapse M2M/OR-filter duplicates
base = TaskItem.objects.filter(id__in=ids)             # clean base for aggregation
```
Aggregating off `base` (a fresh queryset of ids) avoids the `distinct()` + `annotate()` pitfalls that
`OrLookupFilter` and the conjoined `tags` filter can introduce. Aggregations then use
`values(...).annotate(Count(...))` and `Trunc*` functions.

### Completion-only vs whole-set semantics
- `tag_distribution`, `status_breakdown`, `priority_breakdown` reflect the filtered set **as-is**
  (they respect a `completed`/`todo` filter if the user set one).
- Time-based aggregations (`solved_timeline`, `solved_by_tag_timeline`, `calendar_heatmap`,
  `time_to_completion_by_tag`) always restrict to `completed=True, completed_date__isnull=False`,
  because "solved over time" is only meaningful for solved tasks. This is documented in the API
  response and the UI copy.

### M2M counting
Per-tag aggregations join `tags` and therefore count a task once **per tag** it carries (a task with
two tags contributes to both series). `solved_timeline` and `created_vs_completed_timeline` do **not**
join tags, so each task is counted once. `tag_distribution` includes a single `{"slug": null}`
untagged bucket for tasks with no tags.

### Bucketing & timezone
`?bucket=day|week` (default `day`) selects `TruncDay`/`TruncWeek` over `completed_date`, evaluated in
Django's active timezone. `calendar_heatmap` is always daily regardless of `bucket`. The backend
emits only periods that have data; the **frontend fills gaps** to produce continuous axes and running
cumulative sums (for the stacked-area and burn-up charts). Cumulative sums are computed client-side so
the same raw payload serves both cumulative and non-cumulative views.

### Response shape (single payload)
```jsonc
{
  "bucket": "day",
  "totals": { "total": 120, "completed": 80, "open": 40 },
  "tag_distribution": [ { "slug": "urgent", "name": "Urgent", "color": "#ff0000", "count": 34 },
                        { "slug": null, "name": null, "color": null, "count": 5 } ],
  "solved_timeline": [ { "period": "2026-06-01", "count": 3 } ],
  "solved_by_tag_timeline": {
    "periods": ["2026-06-01", "2026-06-02"],
    "series": [ { "slug": "urgent", "name": "Urgent", "color": "#ff0000", "counts": [2, 0] } ]
  },
  "created_vs_completed_timeline": [ { "period": "2026-06-01", "created": 5, "completed": 3 } ],
  "status_breakdown": [ { "status": "idea", "label": "Idee", "count": 20 } ],
  "priority_breakdown": [ { "priority": 4, "label": "Prioritară", "count": 10 } ],
  "calendar_heatmap": [ { "date": "2026-06-01", "count": 3 } ],
  "time_to_completion_by_tag": [ { "slug": "urgent", "name": "Urgent", "color": "#ff0000",
                                   "avg_days": 4.2, "count": 30 } ]
}
```
A single composite payload keeps the page to one round trip; the dataset is per-user and small enough
that computing all sections server-side is cheap.

### Frontend: separate `/tasks/stats` page inheriting filters
- Route added before the catch-all, guarded by `AuthenticatedGuard`.
- `TaskFilters` is reused as the single filter contract. The list's "Stats" link navigates to
  `/tasks/stats` with the current filters serialised as query params; the stats page parses query
  params back into a `TaskFilters` and also renders its own filter bar (tags, search, completed/todo,
  day/week) that writes back to the URL — so the view is bookmarkable and independently usable.
- Charts via **Chart.js core, used directly** (no `ng2-charts`/`ngx-charts` wrapper) to avoid
  Angular-21 peer-dependency lag. A small standalone `ChartCanvasComponent` takes a Chart.js config
  input, creates the chart in an `effect()`, updates on input change, and destroys on teardown.
- Calendar heatmap is a bespoke `CalendarHeatmapComponent` (CSS grid of day cells shaded by count) —
  no extra dependency, and it themes naturally with tag/Bootstrap colors.
- Chart mapping: distribution → horizontal bar (bars colored per tag); solved-per-bucket → bar/line
  with day/week toggle; per-tag cumulative → stacked line with `fill: true` + stacked y-scale;
  burn-up → two cumulative lines; status/priority → doughnut(s); time-to-completion → horizontal bar.

## Risks / Trade-offs
- **Double counting in per-tag charts** → surface a short note in the UI ("multi-tag tasks count in
  each tag") so the stacked-area total legitimately exceeds the solved total.
- **Large date ranges** produce many buckets → default the timeline window to the data's own min/max
  completed_date; week bucketing and client-side gap-filling keep point counts reasonable.
- **Chart.js is another dependency** → justified: no Angular-native lib reliably supports v21 today,
  and Chart.js has no Angular peer dep, so it is the lowest-risk option.

## Migration Plan
No data migration. Purely additive: a new read-only endpoint and a new page. Rollback = remove the
action, the route/component, and the `chart.js` dependency.

## Open Questions
- Should the stats page offer a `month` bucket in addition to `day`/`week`? (Deferred; easy to add
  later — the endpoint can accept `bucket=month` with `TruncMonth`.)
