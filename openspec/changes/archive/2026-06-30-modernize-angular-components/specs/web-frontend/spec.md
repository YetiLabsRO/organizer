## ADDED Requirements

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
