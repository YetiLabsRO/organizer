## MODIFIED Requirements

### Requirement: Task list with filtering
The web app SHALL present a task list that can be filtered by daily focus (today), completed, and
to-do states, by tags, and by a free-text term. Tag pills SHALL be shown at a readable size, and
clicking a tag pill on a task SHALL filter the list to that tag. Each task row SHALL also surface the
task's own attributes at a glance: its **priority** (a coloured accent with a flag for high/low
priority; neutral priority is left unmarked), its **status** as a small badge (omitted for the
default "Idea" status), its **deadline** with visual emphasis when the task is overdue or due soon,
and its owning **project** as a chip.

#### Scenario: Filter the task list
- **WHEN** a user applies a filter (today / completed / tag / text)
- **THEN** the list updates to show only matching tasks

#### Scenario: Click a tag pill to filter
- **WHEN** a user clicks a tag pill shown on a task row
- **THEN** the list filters to tasks carrying that tag, with an active-tag indicator that can be cleared

#### Scenario: Task attributes shown on each row
- **WHEN** the task list is displayed
- **THEN** each row shows the task's priority, non-default status, deadline (emphasised when overdue),
  and project without the user having to open the task

### Requirement: Detail and edit views
The web app SHALL provide detail/edit views for tasks, projects, and tags. The task detail/edit view
SHALL present and allow editing of all task fields — title, description, status, priority, start
date, end date, completed date, estimated time, daily-focus, project, and tags. Tags SHALL be edited
through a single editor showing colored, removable chips with `#` autocomplete (no separate duplicated
tag display), the project SHALL be editable via `@` autocomplete, and the description SHALL be edited
as Markdown with a live preview. Status SHALL be presented as a visual progression of its states
(idea → in progress, with blocked and given-up as branches) whose nodes are selectable, and priority
SHALL be presented as a segmented control; completion SHALL remain a distinct checkbox toggle
separate from status. The task detail view SHALL additionally show read-only context the model
already carries: the task's **comments** (each with author and timestamp) with a control to add a new
comment, a **metadata** area with the created / last-changed / completed dates, and a link to the
**parent task** when one is set.

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

#### Scenario: View and add task comments
- **WHEN** a user opens a task that has comments and submits a new comment
- **THEN** the existing comments are listed with their author and timestamp, and the new comment is
  saved and appears in the list

#### Scenario: See task metadata and parent
- **WHEN** a user opens a task
- **THEN** the created / last-changed / completed dates are shown, and if the task has a parent task a
  link to it is shown

#### Scenario: Set status through the progression and complete via the checkbox
- **WHEN** a user opens a task and selects a state in the status progression, then toggles the
  completion checkbox
- **THEN** the chosen status is applied and highlighted in the progression, and completion is toggled
  independently of the status via its checkbox

#### Scenario: Choose priority with the segmented control
- **WHEN** a user picks Low, Normal, or High in the priority control
- **THEN** the selection is applied and reflected in the control
