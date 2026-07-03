# web-frontend Spec

## Purpose
Provide a single-page web application (Angular) for logging in and managing tasks, projects, and
tags against the REST API.
## Requirements
### Requirement: Authenticated SPA access
The web app SHALL require login before accessing task, project, or tag views, and SHALL attach the
stored authentication token to API requests. Unauthenticated users SHALL be redirected to login.

#### Scenario: Login gates protected routes
- **WHEN** an unauthenticated user navigates to a protected route (e.g. `/tasks`)
- **THEN** they are redirected to the login view

#### Scenario: Token attached to API calls
- **WHEN** a logged-in user triggers an API request
- **THEN** the request carries the `Authorization: Token <key>` header

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

### Requirement: Modern Angular architecture
The web app SHALL be built with standalone components (no `NgModule` declarations), bootstrapped via
`bootstrapApplication`. Components SHALL use `ChangeDetectionStrategy.OnPush`, manage state with
signals, and use the built-in control flow (`@if`, `@for`, `@switch`) in templates instead of the
`*ngIf`/`*ngFor`/`*ngSwitch` structural directives. This requirement constrains implementation only
and SHALL NOT change any user-facing behavior defined by the other web-frontend requirements.

#### Scenario: No NgModules remain
- **WHEN** the application is built
- **THEN** it bootstraps through `bootstrapApplication` and contains no `@NgModule`-declared
  components, pipes, or directives

#### Scenario: Components use OnPush and signals
- **WHEN** a component is reviewed
- **THEN** it declares `ChangeDetectionStrategy.OnPush` and exposes its reactive state via signals

#### Scenario: Templates use built-in control flow
- **WHEN** a template renders conditional or repeated content
- **THEN** it uses `@if`/`@for`/`@switch` rather than `*ngIf`/`*ngFor`/`*ngSwitch`

#### Scenario: Behavior is preserved
- **WHEN** a user logs in and manages tasks, projects, and tags after the migration
- **THEN** authentication, filtering, quick-add, and detail/edit views behave exactly as before

### Requirement: Windowed task list loading
The web app SHALL render the task list with virtualized scrolling backed by a data source that
loads tasks from the paginated API only as needed: it SHALL fetch the pages covering the currently
visible range plus a buffer on each side, SHALL not hold the entire task set in memory or the DOM,
and SHALL show placeholder rows for positions whose data has not yet loaded. Changing a filter or
the search term SHALL reset the window to the top with fresh state.

#### Scenario: Only nearby pages are fetched
- **WHEN** the task list first renders or the user scrolls
- **THEN** the app requests only the pages overlapping the visible range (plus a buffer) rather than
  all tasks

#### Scenario: Placeholders while loading
- **WHEN** the viewport shows positions whose page has not been fetched yet
- **THEN** placeholder rows are shown until the data for those positions arrives

#### Scenario: Filter or search resets the window
- **WHEN** the user changes a filter or the search term
- **THEN** the list reloads from the first page with the new criteria

### Requirement: Server-side task search
The web app SHALL provide a free-text search on the task list that queries the API's `contains`
filter server-side (debounced) and drives the same windowed, paginated loading.

#### Scenario: Search narrows the paginated list
- **WHEN** a user types a search term in the task list
- **THEN** the list reloads showing only tasks whose title or description match, paginated the same
  way as the unfiltered list

### Requirement: Responsive mobile-friendly layout
The web app SHALL present a layout that adapts to small screens: the primary navigation SHALL
collapse into a toggler on narrow viewports, and task rows SHALL remain readable and their controls
tap-friendly on mobile widths.

#### Scenario: Navigation collapses on mobile
- **WHEN** the app is viewed on a narrow (mobile) viewport
- **THEN** the primary navigation collapses behind a toggler that expands it on demand

#### Scenario: Task rows usable on mobile
- **WHEN** the task list is viewed on a narrow viewport
- **THEN** each row's title, tags, and actions remain legible and tappable without horizontal
  overflow

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

### Requirement: Task statistics page
The web app SHALL provide a `/tasks/stats` page, gated by authentication, that visualises statistics
for the task set. The page SHALL inherit the task list's filters via URL query params using the same
`TaskFilters` contract, SHALL expose its own filter controls (tags, free-text, completed/to-do, and a
day/week bucket toggle) that write the current selection back to the URL so the view is bookmarkable,
and SHALL fetch its data from `GET /api/task/stats/`. The task list SHALL offer a link to this page
that carries the currently active filters.

#### Scenario: Open stats from the list with active filters
- **WHEN** a user viewing the task list with a tag and text filter active clicks the "Stats" link
- **THEN** the `/tasks/stats` page opens showing statistics computed from that same filtered set

#### Scenario: Unauthenticated access is gated
- **WHEN** an unauthenticated user navigates to `/tasks/stats`
- **THEN** they are redirected to the login view

#### Scenario: Toggle day/week re-buckets the timeline
- **WHEN** a user on the stats page switches the bucket from day to week
- **THEN** the tasks-solved timeline and per-tag area chart regroup into weekly buckets

### Requirement: Statistics visualisations
The stats page SHALL render, from the `GET /api/task/stats/` payload: a tag-distribution bar chart
(bars colored per tag), a tasks-solved-over-time chart with a day/week toggle, a cumulative
stacked-area chart of tasks solved per tag over time, a calendar heatmap of tasks solved per day, a
burn-up chart of cumulative created vs completed, a status/priority breakdown, and a
time-to-completion-per-tag chart. Charts SHALL be rendered with Chart.js; the calendar heatmap MAY be
a CSS-grid component. The page SHALL show an empty state when there is no matching data and SHALL note
that multi-tag tasks are counted once per tag in the per-tag charts.

#### Scenario: Charts reflect the filtered set
- **WHEN** the stats page loads for a filtered task set
- **THEN** the distribution, timeline, stacked-area, heatmap, burn-up, breakdown, and
  time-to-completion visualisations all reflect that filtered set

#### Scenario: Empty state
- **WHEN** the active filters match no tasks
- **THEN** the page shows an empty state instead of blank charts

