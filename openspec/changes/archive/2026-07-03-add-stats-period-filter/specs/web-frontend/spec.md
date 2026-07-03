## ADDED Requirements

### Requirement: Statistics period selector
The stats page SHALL provide a period selector that scopes the dashboard by completion date, offering
Today, Last week, Last month, and All time presets plus a custom From–To range. The selection SHALL be
stored in the URL (`completed_after` / `completed_before`) so it is bookmarkable and drives the same
filter contract as the rest of the page. When a bounded period is active the totals SHALL present a
completions view (e.g. "completed in period"); "All time" SHALL show the full backlog including open
tasks.

#### Scenario: Choose a preset period
- **WHEN** a user selects the "Last week" preset
- **THEN** the charts and totals reflect only tasks completed in the last week, and the URL carries the
  corresponding `completed_after`/`completed_before` dates

#### Scenario: Custom range
- **WHEN** a user sets a custom From and To date that matches no preset
- **THEN** the dashboard scopes to that window and the selector indicates a custom range

#### Scenario: All time restores the full view
- **WHEN** a user selects "All time"
- **THEN** the completion-date bounds are cleared and the dashboard shows all matching tasks, including
  open tasks in the totals
