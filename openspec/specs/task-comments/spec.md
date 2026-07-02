# task-comments Spec

## Purpose
Let authenticated users attach timestamped comments to tasks.

## Requirements

### Requirement: Comment creation
The system SHALL allow an authenticated user to create a comment on a task with a description, and
SHALL record the comment's author and timestamp.

#### Scenario: Add a comment to a task
- **WHEN** an authenticated user POSTs to `/api/comments/` with a task, user, and description
- **THEN** the comment is stored with a timestamp and associated to the task

### Requirement: Comments included with tasks
The system SHALL include a task's comments when the task is retrieved.

#### Scenario: Retrieve a task with comments
- **WHEN** an authenticated user retrieves a task that has comments
- **THEN** the task response includes its comments

### Requirement: Authenticated access
The system SHALL require authentication for all comment endpoints.

#### Scenario: Unauthenticated request is rejected
- **WHEN** an unauthenticated client requests `/api/comments/`
- **THEN** the request is denied with 401/403
