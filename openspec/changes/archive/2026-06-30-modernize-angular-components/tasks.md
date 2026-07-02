## 1. Bootstrap & routing
- [x] 1.1 Add `app.config.ts` with `provideRouter(routes)`, `provideHttpClient(withInterceptors(...))`,
      `provideAnimations()`, and the service worker provider
- [x] 1.2 Move routes into `app.routes.ts`; convert the token interceptor to a functional interceptor
- [x] 1.3 Switch `main.ts` to `bootstrapApplication(AppComponent, appConfig)`
- [x] 1.4 Delete `app.module.ts` and `app-routing.module.ts`

## 2. Standalone conversion
- [x] 2.1 Make `AppComponent` standalone (imports `RouterOutlet`, `MessagesComponent`, …); remove `standalone: false`
- [x] 2.2 Convert tasks components (`task-list`, `task-detail`) to standalone with explicit imports
- [x] 2.3 Convert projects components (`project-list`, `project-detail`, `project-form`) to standalone
- [x] 2.4 Convert tags components (`tag-list`, `tag-detail`) and `login`, `messages` to standalone
- [x] 2.5 Make pipes (`tag-color`, `reverse-luminance-color`, `slugify`) standalone and import them where used

## 3. Signals & OnPush
- [x] 3.1 Convert `MessageService` (and `AuthService`) reactive state to signals. `ItemCacheService`
      stays a plain internal cache — nothing binds it in a template, so a signal adds no value.
- [x] 3.2 Keep `ProjectService`/`TagService` observable APIs: `ProjectService.project` is a
      `BehaviorSubject` that backs the consumed `getProject()` observable, so it is intentionally
      left as RxJS ("keep observable APIs where consumed"). Component-level state is all signals.
- [x] 3.3 Move task-list filters and component-local state to signals; use `inject()` for dependencies
- [x] 3.4 Add `ChangeDetectionStrategy.OnPush` to every component

## 4. Template control flow
- [x] 4.1 Replace `*ngIf`/`*ngFor`/`*ngSwitch` with `@if`/`@for`/`@switch` across all templates
- [x] 4.2 Ensure `@for` blocks declare a `track` expression

## 5. Tests & verification
- [x] 5.1 Update component specs to import the standalone component directly (drop `AppModule`)
- [x] 5.2 `npm test` green (all specs pass)
- [x] 5.3 `npm run build` (dev + prod) green with no new warnings
- [x] 5.4 Manual smoke test against the running backend: login, task list/filter/quick-add, detail/edit
      for tasks/projects/tags behave unchanged
