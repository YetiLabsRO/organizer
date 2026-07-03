## ADDED Requirements

### Requirement: Paginated task listing
The system SHALL paginate `GET /api/task/` using limit/offset pagination, returning an envelope
`{count, next, previous, results}` where `results` is the current page of tasks. It SHALL apply a
default page size when no `limit` is given and SHALL cap `limit` at a maximum. The list
representation SHALL omit nested comments; the per-task detail representation SHALL include them.

#### Scenario: Default page returned
- **WHEN** an authenticated user GETs `/api/task/` with no `limit`
- **THEN** the response is `{count, next, previous, results}` with at most the default page size in
  `results` and `count` equal to the total matching tasks

#### Scenario: Explicit window with offset
- **WHEN** an authenticated user GETs `/api/task/?limit=50&offset=100`
- **THEN** `results` contains the 50 tasks starting at offset 100 in the ordered set

#### Scenario: Limit is capped
- **WHEN** an authenticated user requests a `limit` above the maximum
- **THEN** the response returns no more than the maximum page size

#### Scenario: List omits comments, detail includes them
- **WHEN** a task is fetched via the list endpoint versus `GET /api/task/{id}/`
- **THEN** the list item has no nested `comments` while the detail response includes them

### Requirement: Task ownership scoping
The system SHALL scope the task list and task detail to the authenticated user's own tasks, and
SHALL set the owner of a task to the creating user on creation.

#### Scenario: Only own tasks are listed
- **WHEN** an authenticated user lists `/api/task/`
- **THEN** only tasks owned by that user are returned

#### Scenario: New task is owned by its creator
- **WHEN** an authenticated user creates a task via `POST /api/task/`
- **THEN** the created task's `owner` is that user, regardless of any `owner` sent in the request

### Requirement: Combined today view filter
The system SHALL provide a `today_view` filter that returns, in a single query, tasks flagged
`for_today` together with tasks completed on the current day, so the combined daily view is one
paginable request.

#### Scenario: Today view combines focus and completed-today
- **WHEN** an authenticated user GETs `/api/task/?today_view=true`
- **THEN** the results include tasks with `for_today = true` and tasks whose completion date is today

## MODIFIED Requirements

### Requirement: Task ordering
The system SHALL return tasks ordered by most recently changed first (`changed_date` descending),
with the task primary key as a final tiebreaker so the ordering is deterministic and pagination is
stable across requests. Because `changed_date` is updated on every save, editing or toggling a task
SHALL move it to the top of the list.

#### Scenario: Tasks returned most-recently-changed first
- **WHEN** an authenticated user lists `/api/task/`
- **THEN** tasks are returned sorted by `changed_date` descending, with `pk` breaking ties

#### Scenario: Editing a task floats it to the top
- **WHEN** an authenticated user updates or toggles a task
- **THEN** that task appears first on the next listing

#### Scenario: Stable ordering across pages
- **WHEN** an authenticated user requests successive pages of `/api/task/`
- **THEN** no task is duplicated or skipped between adjacent pages
