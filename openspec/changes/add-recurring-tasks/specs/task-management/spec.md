## ADDED Requirements

### Requirement: Task template linkage
The system SHALL allow a task to reference the recurring template that generated it. Tasks created by
hand SHALL have no template reference. When a template is deleted, its generated tasks SHALL be
retained with the template reference cleared. The task API SHALL expose the template reference as a
read-only field so clients can identify recurring-generated tasks.

#### Scenario: Generated task references its template
- **WHEN** a task is created by the recurring-task generation process
- **THEN** the task's `template` field references the originating template

#### Scenario: Manually created task has no template
- **WHEN** an authenticated user POSTs a task to `/api/task/`
- **THEN** the task's `template` field is null

#### Scenario: Deleting a template retains its tasks
- **WHEN** a template with previously generated tasks is deleted
- **THEN** those tasks remain and their `template` reference is cleared
