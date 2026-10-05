## ADDED Requirements

### Requirement: Tasks owned by another integration are excluded
The Notion push SHALL NOT create a Notion page for a task that carries a VolunHub link, whether that
link is active or marked removed, so that each task has at most one external owner.

#### Scenario: VolunHub task is not mirrored to Notion
- **WHEN** a user has both Notion and VolunHub connected and a task was imported from VolunHub
- **THEN** the Notion sync does not create a page for that task

#### Scenario: Removed VolunHub task stays out of Notion
- **WHEN** a VolunHub-linked task is marked removed from VolunHub
- **THEN** the Notion sync still does not create a page for it
