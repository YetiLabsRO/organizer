# tag-management Spec

## Purpose
Let authenticated users define color-coded tags used to label and filter tasks and projects.
## Requirements
### Requirement: Tag creation and attributes
The system SHALL allow an authenticated user to create a tag with a name and optional description
and color (default `#FFFFFF`), and SHALL derive a unique slug from the name when none is provided.
The description SHALL be stored as free text of unbounded length so it can hold Markdown content.

#### Scenario: Create a tag without a slug
- **WHEN** an authenticated user POSTs to `/api/tag/` with a name and no slug
- **THEN** the tag is created with a slug derived from the name

#### Scenario: Tag carries a color
- **WHEN** a tag is created with a color value
- **THEN** the color is persisted and returned

#### Scenario: Description holds long Markdown text
- **WHEN** a tag is saved with a multi-line Markdown description
- **THEN** the full description is persisted and returned unmodified

### Requirement: Tag usage count
The system SHALL expose, for each tag, the number of tasks currently associated with it.

#### Scenario: Tag reports its task count
- **WHEN** an authenticated user retrieves a tag
- **THEN** the response includes a `count` of tasks using that tag

### Requirement: Tag lookup by slug
The system SHALL allow filtering tags by slug.

#### Scenario: Fetch a tag by slug
- **WHEN** an authenticated user GETs `/api/tag/?slug=urgent`
- **THEN** only the tag with slug `urgent` is returned

### Requirement: Authenticated access
The system SHALL require authentication for all tag endpoints.

#### Scenario: Unauthenticated request is rejected
- **WHEN** an unauthenticated client requests `/api/tag/`
- **THEN** the request is denied with 401/403

