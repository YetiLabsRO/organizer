# project-management Spec

## Purpose
Let authenticated users group tasks into projects that carry their own metadata and tags.
## Requirements
### Requirement: Project creation and attributes
The system SHALL allow an authenticated user to create a project with a title and optional
description, slug, start date, and end date. When no slug is provided, the system SHALL derive one
from the title. Editing an existing project SHALL update that project rather than create a second
one, and its start/end dates SHALL survive the round trip through the edit form.

#### Scenario: Create a project without a slug
- **WHEN** an authenticated user POSTs to `/api/project/` with a title and no slug
- **THEN** the project is created with a slug derived from the title

#### Scenario: Project dates are formatted as day/month/year
- **WHEN** a project with start/end dates is retrieved
- **THEN** the dates are serialized in `DD/MM/YYYY` format

#### Scenario: Editing an existing project updates it
- **WHEN** a user opens an existing project's edit form, changes a field, and saves
- **THEN** that project is updated in place and no duplicate project is created

### Requirement: Project tags
The system SHALL allow a project to carry multiple tags, which are inherited by tasks assigned to
the project.

#### Scenario: Assign tags to a project
- **WHEN** an authenticated user sets tags on a project
- **THEN** the project persists those tags and tasks added to it inherit them

### Requirement: Authenticated access
The system SHALL require authentication for all project endpoints.

#### Scenario: Unauthenticated request is rejected
- **WHEN** an unauthenticated client requests `/api/project/`
- **THEN** the request is denied with 401/403

