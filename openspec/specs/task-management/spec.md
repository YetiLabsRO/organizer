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
The system SHALL allow tasks to carry an integer `order` and SHALL return tasks ordered by `order`,
then descending priority, then start date, then change/creation date.

#### Scenario: Tasks returned in order
- **WHEN** an authenticated user lists `/api/task/`
- **THEN** tasks are returned sorted by `order`, then by priority and dates

### Requirement: Project and tag association
The system SHALL allow a task to belong to a project and to carry multiple tags. When a task is
saved, it SHALL inherit the tags of its associated project.

#### Scenario: Task inherits project tags on save
- **WHEN** a task assigned to a project is saved
- **THEN** the project's tags are added to the task's tags

### Requirement: Task filtering and search
The system SHALL allow authenticated users to filter tasks by completed state, status, priority,
tags (by slug), completion date, owner, start/end dates, and `for_today`, and to search by a
`contains` term matching the title or description.

#### Scenario: Search by free text
- **WHEN** an authenticated user GETs `/api/task/?contains=report`
- **THEN** tasks whose title or description contain "report" (case-insensitive) are returned

#### Scenario: Filter by tag slug
- **WHEN** an authenticated user GETs `/api/task/?tags=urgent`
- **THEN** only tasks tagged with the `urgent` slug are returned

### Requirement: Authenticated access
The system SHALL require authentication for all task endpoints.

#### Scenario: Unauthenticated request is rejected
- **WHEN** an unauthenticated client requests `/api/task/`
- **THEN** the request is denied with 401/403
