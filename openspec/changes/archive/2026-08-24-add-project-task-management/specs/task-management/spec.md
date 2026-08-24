## MODIFIED Requirements

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
