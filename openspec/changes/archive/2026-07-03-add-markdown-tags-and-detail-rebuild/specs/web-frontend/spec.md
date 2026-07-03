## MODIFIED Requirements

### Requirement: Task list with filtering
The web app SHALL present a task list that can be filtered by daily focus (today), completed, and
to-do states, by tags, and by a free-text term. Tag pills SHALL be shown at a readable size, and
clicking a tag pill on a task SHALL filter the list to that tag.

#### Scenario: Filter the task list
- **WHEN** a user applies a filter (today / completed / tag / text)
- **THEN** the list updates to show only matching tasks

#### Scenario: Click a tag pill to filter
- **WHEN** a user clicks a tag pill shown on a task row
- **THEN** the list filters to tasks carrying that tag, with an active-tag indicator that can be cleared

### Requirement: Quick task add
The web app SHALL allow quickly adding a task from the list view. Tags SHALL be assigned inline by
typing `#tagname` and the project by typing `@projectname`, each offering an autocomplete dropdown
(tags shown in their colors) while typing. On submission the tokens are resolved and removed from the
task title.

#### Scenario: Quick-add a task with a tag and project
- **WHEN** a user types a task title containing `#urgent` and `@website` and submits
- **THEN** the task is created tagged `urgent` and assigned to project `website`, with the tokens
  removed from the stored title, and it appears in the list

#### Scenario: Autocomplete while typing a token
- **WHEN** a user types `#` (or `@`) followed by text in the quick-add field
- **THEN** a dropdown of matching tags (in their colors) or projects is shown and a selection inserts
  the canonical token

### Requirement: Detail and edit views
The web app SHALL provide detail/edit views for tasks, projects, and tags. The task detail/edit view
SHALL present and allow editing of all task fields — title, description, status, priority, start
date, end date, completed date, estimated time, daily-focus, project, and tags. Tags SHALL be edited
through a single editor showing colored, removable chips with `#` autocomplete (no separate duplicated
tag display), the project SHALL be editable via `@` autocomplete, and the description SHALL be edited
as Markdown with a live preview.

#### Scenario: Open a task detail view
- **WHEN** a user selects a task from the list
- **THEN** the task's detail/edit view is shown with all its fields

#### Scenario: Edit tags without duplication
- **WHEN** a user edits a task's tags
- **THEN** tags appear once, as colored removable chips, added via `#` autocomplete

#### Scenario: Edit description as Markdown with preview
- **WHEN** a user edits the description
- **THEN** a Markdown editor with a live rendered preview is shown, and the saved value renders as
  Markdown

#### Scenario: Manage projects and tags
- **WHEN** a user opens a project or tag
- **THEN** its detail/edit view is shown and changes can be saved

## ADDED Requirements

### Requirement: Markdown rendering of descriptions
The web app SHALL render task and tag descriptions as Markdown (rather than raw text), both in the
task list (clamped to the row) and in the detail views. Rendered Markdown SHALL be sanitized so that
scripts and event handlers are not executed.

#### Scenario: Task description renders as Markdown in the list
- **WHEN** a task with a Markdown description is shown in the list
- **THEN** its description is rendered (e.g. emphasis, links) and clamped to the row, not shown as raw
  Markdown

#### Scenario: Rendered Markdown is sanitized
- **WHEN** a description contains a `<script>` or inline event handler
- **THEN** the rendered output does not execute it

### Requirement: Inline tag and project autocomplete
The web app SHALL provide an inline autocomplete for `#` (tags) and `@` (projects) usable in the
quick-add field and the task detail tag editor: typing a trigger character followed by text SHALL
show a dropdown of matching entities (tags in their colors), navigable by keyboard and selectable by
click, inserting the chosen entity.

#### Scenario: Keyboard-driven selection
- **WHEN** a user types a `#`/`@` token and uses arrow keys then Enter
- **THEN** the highlighted tag/project is inserted

#### Scenario: No match
- **WHEN** the typed token matches no tag/project
- **THEN** the dropdown shows an empty/no-results state and typing continues normally
