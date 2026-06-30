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
to-do states, by tags, and by a free-text term.

#### Scenario: Filter the task list
- **WHEN** a user applies a filter (today / completed / tag / text)
- **THEN** the list updates to show only matching tasks

### Requirement: Quick task add
The web app SHALL allow quickly adding a task from the list view, including assigning tags as part
of quick entry.

#### Scenario: Quick-add a task with tags
- **WHEN** a user quick-adds a task and specifies tags
- **THEN** the task is created with those tags and appears in the list

### Requirement: Detail and edit views
The web app SHALL provide detail/edit views for tasks, projects, and tags.

#### Scenario: Open a task detail view
- **WHEN** a user selects a task from the list
- **THEN** the task's detail/edit view is shown

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

