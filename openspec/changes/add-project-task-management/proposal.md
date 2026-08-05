# Change: Make the project detail view a working project workspace

## Why
The project detail view is effectively broken and, where it works, near-empty. It renders a title,
a description, the project's tags and an Edit button — nothing else. In particular:

- **It usually renders blank.** `ProjectService` only pushes a fetched project onto its subject from
  inside the tag-resolution callback, so a project with **no tags** never emits and the page shows an
  empty card with just the Edit button.
- **A project's tasks are nowhere to be seen.** Tasks carry a `project` FK and the tag detail view
  already embeds the task list scoped to its tag, but there is no equivalent for projects — and the
  task API has no `project` filter to make it possible.
- **You cannot add a task to a project from the project.** The only route to it is remembering to
  pick the project in the create-task drawer, or typing `@slug` in quick-add.
- **Edit corrupts.** The form the Edit button opens always calls `createProject`, so saving an
  existing project would create a duplicate — and it stamps a bogus `{year, month, day}` value over
  the loaded start date, which the API rejects, so an edit cannot be saved at all.

## What Changes
- **Task API:** `TaskFilterSet` gains a `project` filter, so `/api/task/?project=<id>` returns one
  project's tasks (owner-scoped and paginated like every other task query).
- **Project detail view** becomes the project's workspace:
  - a proper header — title, Markdown description, start/end dates, tag pills, and the task count,
  - the project's **tasks listed** below it, reusing the existing task list (filters, search,
    quick-add, virtual scroll, live sync) scoped to the project,
  - a **New Task** action that opens the app-wide Create Task drawer — the same UI as everywhere
    else — **pre-filled with this project**, so the created task lands in the project,
  - quick-add inside the project list also defaults to the project.
- **Create-task drawer** accepts an optional preset (project) when opened, via `TaskDrawerService`.
- **Fixes:** `ProjectService.getProject` emits regardless of whether the project has tags (and stops
  leaking the previously-viewed project to the next detail view); the project form updates an
  existing project instead of creating a copy, and round-trips its dates.

Non-goals: project-level statistics, per-project progress charts, owner-scoping of projects
(the `Project` model has no owner today), and a redesign of the project form beyond making save work.

## Impact
- Affected specs:
  - **task-management** (MODIFIED): task list filterable by project.
  - **web-frontend** (MODIFIED): project detail lists the project's tasks and can create tasks into it.
  - **project-management** (MODIFIED): editing a project updates it rather than creating a new one.
- Affected code:
  - `tasks/filters.py`, `tasks/tests.py` — the `project` filter + tests.
  - `frontend/src/app/projects/project.service.ts` — emit fix.
  - `frontend/src/app/projects/project-details/*` — the rebuilt detail view.
  - `frontend/src/app/projects/project-form/project-form.component.ts` — update vs create, dates.
  - `frontend/src/app/tasks/task-filters.ts`, `task-list/*`, `task-drawer.service.ts`,
    `task-create-drawer/*`, `task-stats/*` — project scoping and the drawer preset.
