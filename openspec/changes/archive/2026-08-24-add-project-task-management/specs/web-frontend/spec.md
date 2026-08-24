## ADDED Requirements

### Requirement: Project detail workspace
The project detail view SHALL present the project as a workspace rather than a title card: a header
with the project's title, its description rendered as Markdown, its start/end dates and tag pills,
and the project's tasks listed below it. The task list SHALL be the app's regular task list —
same rows, filters, search, quick-add, and live sync — scoped to that project. The view SHALL offer
a **New Task** action that opens the app-wide Create Task drawer (the same creation UI used
everywhere else) pre-filled with this project, and any task created from the project view —
through the drawer or the inline quick-add — SHALL be assigned to that project without the user
selecting it. The header SHALL render even when the project has no tags.

#### Scenario: Open a project
- **WHEN** a user opens a project from the project list
- **THEN** the project's title, description, dates, and tags are shown, followed by the tasks
  assigned to that project

#### Scenario: A project without tags still renders
- **WHEN** a user opens a project that has no tags
- **THEN** the project's details are shown (the view is not blank)

#### Scenario: Create a task from the project view
- **WHEN** a user chooses New Task on a project and submits the drawer
- **THEN** the drawer opens with that project already selected, and the created task is assigned to
  the project and appears in the project's task list

#### Scenario: Quick-add inside a project
- **WHEN** a user quick-adds a task from the project's task list without typing an `@project` token
- **THEN** the task is created in that project
