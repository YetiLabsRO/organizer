# Change: Modernize the Angular SPA to standalone + signals + OnPush

## Why
The `frontend/` SPA was migrated to Angular 21 but kept its legacy **NgModule** architecture with
default change detection and `*ngIf`/`*ngFor` templates. Angular's current idioms — standalone
components, signals, `OnPush`, and the `@if`/`@for`/`@switch` control flow — are the supported,
better-performing direction and are already the stated convention for new code (`frontend/CLAUDE.md`,
`.junie/guidelines.md`). This change pays down that gap deliberately, without altering behavior.

## What Changes
- Bootstrap the app with `bootstrapApplication` + `provideRouter`/`provideHttpClient` instead of
  `AppModule` + `platformBrowser().bootstrapModule(...)`; remove `app.module.ts`/`app-routing.module.ts`.
- Convert every component, pipe, and directive to **standalone** (drop the `standalone: false`
  flags) and have each import its own dependencies.
- Adopt **signals** for component/service state (e.g. the message list, project/tag caches,
  task-list filters) and `inject()` over constructor injection where it reads better.
- Set `ChangeDetectionStrategy.OnPush` on all components.
- Replace structural directives in templates with the new control flow (`@if`/`@for`/`@switch`).
- Update unit specs to the standalone TestBed pattern (import the component directly instead of
  `AppModule`); keep them green.
- **No user-facing behavior change** — routes, auth flow, filtering, quick-add, and detail/edit
  views remain identical.

## Impact
- Affected specs: `web-frontend` (adds a non-functional "Modern Angular architecture" requirement;
  existing behavioral requirements are unchanged).
- Affected code: all of `frontend/src/app/**` (components, services, pipes, `main.ts`), removal of
  `app.module.ts` and `app-routing.module.ts`, and the `*.spec.ts` files.
- No backend impact.
