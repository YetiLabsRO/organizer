## MODIFIED Requirements

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
