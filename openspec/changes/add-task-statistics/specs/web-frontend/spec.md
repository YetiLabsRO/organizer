## ADDED Requirements

### Requirement: Task statistics page
The web app SHALL provide a `/tasks/stats` page, gated by authentication, that visualises statistics
for the task set. The page SHALL inherit the task list's filters via URL query params using the same
`TaskFilters` contract, SHALL expose its own filter controls (tags, free-text, completed/to-do, and a
day/week bucket toggle) that write the current selection back to the URL so the view is bookmarkable,
and SHALL fetch its data from `GET /api/task/stats/`. The task list SHALL offer a link to this page
that carries the currently active filters.

#### Scenario: Open stats from the list with active filters
- **WHEN** a user viewing the task list with a tag and text filter active clicks the "Stats" link
- **THEN** the `/tasks/stats` page opens showing statistics computed from that same filtered set

#### Scenario: Unauthenticated access is gated
- **WHEN** an unauthenticated user navigates to `/tasks/stats`
- **THEN** they are redirected to the login view

#### Scenario: Toggle day/week re-buckets the timeline
- **WHEN** a user on the stats page switches the bucket from day to week
- **THEN** the tasks-solved timeline and per-tag area chart regroup into weekly buckets

### Requirement: Statistics visualisations
The stats page SHALL render, from the `GET /api/task/stats/` payload: a tag-distribution bar chart
(bars colored per tag), a tasks-solved-over-time chart with a day/week toggle, a cumulative
stacked-area chart of tasks solved per tag over time, a calendar heatmap of tasks solved per day, a
burn-up chart of cumulative created vs completed, a status/priority breakdown, and a
time-to-completion-per-tag chart. Charts SHALL be rendered with Chart.js; the calendar heatmap MAY be
a CSS-grid component. The page SHALL show an empty state when there is no matching data and SHALL note
that multi-tag tasks are counted once per tag in the per-tag charts.

#### Scenario: Charts reflect the filtered set
- **WHEN** the stats page loads for a filtered task set
- **THEN** the distribution, timeline, stacked-area, heatmap, burn-up, breakdown, and
  time-to-completion visualisations all reflect that filtered set

#### Scenario: Empty state
- **WHEN** the active filters match no tasks
- **THEN** the page shows an empty state instead of blank charts
