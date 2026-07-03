## ADDED Requirements

### Requirement: Recurring template management UI
The web frontend SHALL provide a screen to manage recurring task templates, reachable from the main
navigation. It SHALL list the user's templates with their schedule summary, next occurrence, and
active state, and SHALL let the user create, edit, pause/activate, delete, and run a template now.
The create/edit form SHALL include a recurrence editor whose inputs adapt to the chosen frequency
(day-of-month for monthly/yearly, weekday selection for weekly, interval for all), plus lead time and
a skip-while-previous-open toggle, and SHALL reuse the existing project picker and tag input.

#### Scenario: View and manage templates
- **WHEN** the user opens the templates screen
- **THEN** their templates are listed with schedule summary, next occurrence, and active state, each
  offering edit, pause/activate, delete, and run-now actions

#### Scenario: Recurrence editor adapts to frequency
- **WHEN** the user selects the monthly frequency in the template form
- **THEN** a day-of-month input is shown, and the weekday selector shown for weekly is hidden

### Requirement: Recurring task indicator
The web frontend SHALL visually indicate tasks that were generated from a template and SHALL let the
user navigate from such a task to its originating template.

#### Scenario: Generated task is marked as recurring
- **WHEN** a task that was generated from a template is shown in the task list or detail view
- **THEN** a recurring indicator is displayed that links to the originating template
