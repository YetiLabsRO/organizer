## MODIFIED Requirements

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
