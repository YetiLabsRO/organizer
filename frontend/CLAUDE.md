# frontend/CLAUDE.md

Angular single-page app for Organizer. Consumes the Django REST API at the repo root.

## Stack
- **Angular 21** (standalone — bootstrapped via `bootstrapApplication` in `src/main.ts`, providers in
  `src/app/app.config.ts`, routes in `src/app/app.routes.ts`). Components are standalone with
  `OnPush` change detection and signals for state; templates use `@if`/`@for` control flow.
  Note: Angular 22 is newer but requires Node ≥ 22.22; this app targets 21 to run on Node 20.
- Build: `@angular/build:application` builder (see `angular.json`).
- UI: ng-bootstrap + Bootstrap 5 + Angular Material (indigo-pink theme), ngx-chips (tag input),
  ngx-color-picker. PWA via `@angular/service-worker` (`ngsw-config.json`).
- RxJS 7, TypeScript 5.9, zone.js.

## Commands
```bash
npm install          # install deps
npm start            # ng serve on http://localhost:4200
npm run build        # production build to dist/organizer-frontend
npm test             # unit tests (Angular @angular/build:unit-test / vitest)
```

## Backend wiring
- API base URL comes from `src/environments/environment.ts` (`apiBase`); prod uses same-origin
  (`environment.prod.ts`, `apiBase: ''`). Do NOT hardcode `http://127.0.0.1:8000` in services —
  use `environment.apiBase`.
- Auth: token stored in `localStorage`, attached as `Authorization: Token <key>` by
  `src/app/http-interceptors/token.interceptor.ts`. Login hits `/rest-auth/login/`.
- The Django backend must allow the dev origin (`CORS_ALLOWED_ORIGINS` includes
  `http://localhost:4200`).

## Conventions for new/changed code
The app is fully modern Angular — keep it that way:
- **Standalone** components (no NgModules), **signals** for reactive state, `ChangeDetectionStrategy.OnPush`.
- New control flow `@if` / `@for` (with `track`) / `@switch` in templates (not `*ngIf`/`*ngFor`).
- `inject()` over constructor injection where it reads better.
- Services that back a consumed observable API may keep RxJS (e.g. `ProjectService.project`); prefer
  signals for component-held state.

## Known follow-ups
- Unit tests run on `@angular/build:unit-test` (vitest + jsdom) via `npm test`. Component specs
  import `AppModule` and add `provideHttpClientTesting()` + `provideRouter([])`; service specs use
  `provideHttpClient()` + `provideHttpClientTesting()`. They are "should create" smoke tests —
  add real assertions as behavior is reworked.
- ngx-chips has loose Angular peer ranges; watch for issues when bumping Angular further.
