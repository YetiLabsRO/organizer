# task-management Spec

## Purpose
Let authenticated users create, organize, filter, and complete tasks, including sub-tasks,
prioritization, daily focus, and project/tag association.
## Requirements
### Requirement: Task creation and attributes
The system SHALL allow an authenticated user to create a task with a title and optional
description, status, priority, start date, end date (deadline), and estimated time. Status SHALL be
one of idea, blocked, inprogress, or givenup (default idea). Priority SHALL be one of high, normal,
or low (default normal).

#### Scenario: Create a minimal task
- **WHEN** an authenticated user POSTs to `/api/task/` with a title
- **THEN** the task is created with status `idea` and priority `normal`

#### Scenario: Create a task with full attributes
- **WHEN** an authenticated user POSTs a title, description, status, priority, and dates
- **THEN** the task persists all provided attributes and returns them

### Requirement: Task completion
The system SHALL allow marking a task completed, and SHALL record the completion timestamp when a
task transitions to completed and clear it when the task is no longer completed.

#### Scenario: Completing a task records the timestamp
- **WHEN** a task is updated with `completed = true`
- **THEN** `completed_date` is set to the time of completion

#### Scenario: Un-completing a task clears the timestamp
- **WHEN** a previously completed task is updated with `completed = false`
- **THEN** `completed_date` is cleared

### Requirement: Daily focus flag
The system SHALL provide a `for_today` boolean on tasks so users can mark tasks to focus on today,
and SHALL allow filtering tasks by this flag.

#### Scenario: Filter tasks marked for today
- **WHEN** an authenticated user GETs `/api/task/?for_today=true`
- **THEN** only tasks with `for_today = true` are returned

### Requirement: Sub-tasks
The system SHALL allow a task to reference a parent task. When a parent task is deleted, child tasks
SHALL be retained with their parent reference cleared.

#### Scenario: Create a sub-task
- **WHEN** a task is created with `parent_task` set to an existing task's id
- **THEN** the task is linked to that parent

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

### Requirement: Project and tag association
The system SHALL allow a task to belong to a project and to carry multiple tags. When a task is
saved, it SHALL inherit the tags of its associated project.

#### Scenario: Task inherits project tags on save
- **WHEN** a task assigned to a project is saved
- **THEN** the project's tags are added to the task's tags

### Requirement: Task filtering and search
The system SHALL allow authenticated users to filter tasks by completed state, status, priority,
tags (by slug), completion date, owner, start/end dates, `for_today`, and **project**, and to search
by a `contains` term matching the title or description.

#### Scenario: Search by free text
- **WHEN** an authenticated user GETs `/api/task/?contains=report`
- **THEN** tasks whose title or description contain "report" (case-insensitive) are returned

#### Scenario: Filter by tag slug
- **WHEN** an authenticated user GETs `/api/task/?tags=urgent`
- **THEN** only tasks tagged with the `urgent` slug are returned

#### Scenario: Filter by project
- **WHEN** an authenticated user GETs `/api/task/?project=<id>`
- **THEN** only that user's tasks assigned to that project are returned, in the same paginated
  envelope as an unfiltered list

#### Scenario: Project filter combines with the other filters
- **WHEN** an authenticated user GETs `/api/task/?project=<id>&completed=false`
- **THEN** only that project's not-yet-completed tasks are returned

### Requirement: Authenticated access
The system SHALL require authentication for all task endpoints.

#### Scenario: Unauthenticated request is rejected
- **WHEN** an unauthenticated client requests `/api/task/`
- **THEN** the request is denied with 401/403

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

