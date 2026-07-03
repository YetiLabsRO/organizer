## ADDED Requirements

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
