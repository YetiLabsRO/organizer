## MODIFIED Requirements

### Requirement: Comment creation
The system SHALL allow an authenticated user to create a comment on a task with a description, and
SHALL record the comment's author as the **authenticated user** (the author is derived from the
request, not supplied by the client) together with a timestamp.

#### Scenario: Add a comment to a task
- **WHEN** an authenticated user POSTs to `/api/comments/` with a task and description
- **THEN** the comment is stored with a timestamp, authored by the requesting user, and associated to
  the task

#### Scenario: Author is not client-controlled
- **WHEN** an authenticated user POSTs a comment while attempting to set a different `user`
- **THEN** the stored comment's author is the authenticated user, ignoring the supplied value

## ADDED Requirements

### Requirement: Comment ownership scoping
The system SHALL scope the comment endpoint to the requesting user's own tasks: listing and
retrieving comments SHALL only return comments on tasks the user owns.

#### Scenario: Comments on another user's task are not visible
- **WHEN** an authenticated user lists `/api/comments/`
- **THEN** only comments on that user's own tasks are returned, never comments on other users' tasks
