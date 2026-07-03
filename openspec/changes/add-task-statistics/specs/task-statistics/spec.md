## ADDED Requirements

### Requirement: Filtered statistics endpoint
The system SHALL provide a read-only `GET /api/task/stats/` endpoint that requires authentication,
is scoped to the authenticated user's own tasks, and applies the same `TaskFilterSet` filters as
`GET /api/task/` (tags, `contains`, `completed`, `status`, `priority`, dates, `for_today`,
`today_view`). It SHALL accept `?bucket=day|week` (default `day`) selecting the time-grouping for the
timeline sections, and SHALL reject an unsupported `bucket` value. It SHALL return a single JSON
payload containing all statistics sections.

#### Scenario: Unauthenticated request is rejected
- **WHEN** an unauthenticated client requests `GET /api/task/stats/`
- **THEN** the request is denied with 401/403

#### Scenario: Only the caller's tasks are aggregated
- **WHEN** an authenticated user requests `GET /api/task/stats/`
- **THEN** every returned aggregate is computed only from tasks owned by that user

#### Scenario: Filters are honoured
- **WHEN** an authenticated user requests `GET /api/task/stats/?tags=urgent&contains=report`
- **THEN** the aggregates are computed from exactly the tasks that `GET /api/task/?tags=urgent&contains=report` would return

#### Scenario: Invalid bucket rejected
- **WHEN** an authenticated user requests `GET /api/task/stats/?bucket=fortnight`
- **THEN** the request fails with a 400 validation error

### Requirement: Tag distribution
The stats payload SHALL include a `tag_distribution` section giving the number of tasks per tag over
the filtered set, where a task carrying multiple tags is counted once for each of its tags, and
tasks with no tags are reported in a single untagged bucket. Each entry SHALL carry the tag's slug,
name, and color (null for the untagged bucket).

#### Scenario: Task counted under each of its tags
- **WHEN** the filtered set contains a task tagged both `urgent` and `work`
- **THEN** `tag_distribution` counts that task under `urgent` and under `work`

#### Scenario: Untagged bucket
- **WHEN** the filtered set contains tasks with no tags
- **THEN** `tag_distribution` includes one bucket with `slug: null` counting those tasks

### Requirement: Completion timeline and calendar
The stats payload SHALL include a `solved_timeline` section counting completed tasks grouped by the
requested `bucket` over `completed_date`, and a `calendar_heatmap` section counting completed tasks
per calendar day. Both sections SHALL consider only tasks with `completed = true` and a non-null
`completed_date`, and SHALL count each task once. Time grouping SHALL be evaluated in the server's
active timezone.

#### Scenario: Solved tasks grouped per day
- **WHEN** an authenticated user requests `GET /api/task/stats/?bucket=day`
- **THEN** `solved_timeline` has one entry per day that has completed tasks, with the count of tasks completed that day

#### Scenario: Solved tasks grouped per week
- **WHEN** an authenticated user requests `GET /api/task/stats/?bucket=week`
- **THEN** `solved_timeline` groups the same completed tasks into week buckets

#### Scenario: Non-completed tasks excluded from the timeline
- **WHEN** the filtered set contains tasks that are not completed
- **THEN** those tasks do not contribute to `solved_timeline` or `calendar_heatmap`

### Requirement: Per-tag solved timeline
The stats payload SHALL include a `solved_by_tag_timeline` section that reports, for each tag,
the number of completed tasks per time bucket, so a cumulative stacked-area chart can be drawn. A
task carrying multiple tags SHALL contribute to each of its tags' series.

#### Scenario: Per-tag buckets returned
- **WHEN** an authenticated user requests `GET /api/task/stats/?bucket=week`
- **THEN** `solved_by_tag_timeline` returns, per tag, a completed-task count for each week bucket

#### Scenario: Multi-tag task contributes to each series
- **WHEN** a completed task is tagged both `urgent` and `work`
- **THEN** it increments both the `urgent` and the `work` series in its bucket

### Requirement: Burn-up created vs completed
The stats payload SHALL include a `created_vs_completed_timeline` section giving, per time bucket, the
number of tasks created (by `created_date`) and the number of tasks completed (by `completed_date`)
within the filtered set, so a burn-up of cumulative created vs cumulative completed can be drawn.

#### Scenario: Created and completed counts per bucket
- **WHEN** an authenticated user requests `GET /api/task/stats/`
- **THEN** each `created_vs_completed_timeline` entry carries both a `created` and a `completed` count for its period

### Requirement: Status and priority breakdown
The stats payload SHALL include `status_breakdown` and `priority_breakdown` sections counting tasks in
the filtered set per status value and per priority value, each entry carrying the raw value, its human
label, and the count.

#### Scenario: Counts per status and priority
- **WHEN** an authenticated user requests `GET /api/task/stats/`
- **THEN** `status_breakdown` sums to the filtered task total across statuses and `priority_breakdown` sums to it across priorities

### Requirement: Time to completion per tag
The stats payload SHALL include a `time_to_completion_by_tag` section giving, per tag, the average
elapsed time from `created_date` to `completed_date` across that tag's completed tasks, together with
the number of completed tasks contributing to the average.

#### Scenario: Average lead time per tag
- **WHEN** a tag's completed tasks took on average four days from creation to completion
- **THEN** that tag's `time_to_completion_by_tag` entry reports an average of about four days and the contributing task count
