# Tasks: Make the project detail view a working project workspace

## 1. Backend — filter tasks by project
- [x] 1.1 `TaskFilterSet`: add a `project` filter (`ModelChoiceFilter` over `Project`) and list it in
      `Meta.fields`, so `/api/task/?project=<id>` narrows the owner-scoped list.
- [x] 1.2 Tests: filtering by project returns only that project's tasks, stays owner-scoped, combines
      with the existing filters, and rejects a non-existent project id.
- [x] 1.3 `ProjectSerializer`: allow null start/end dates (the model already does), so a project
      without dates can be saved at all; tests for create/update and the `DD/MM/YYYY` output.

## 2. Frontend — service fixes
- [x] 2.1 `ProjectService.getProject`: emit the fetched project whether or not it has tags, clear the
      previously-viewed project first so a detail view never shows the last project, and resolve tags
      without pushing list projects onto the detail subject.
- [x] 2.2 `ProjectService.fetchProject`: a completing, error-propagating fetch so a view can tell
      "loading" from "no such project"; invalidate the cached project list on create/update.

## 3. Frontend — project-scoped task list
- [x] 3.1 `TaskFilters`: carry an optional `project` id in the query string and in the router query
      params (so the Stats link keeps the project scope); parse it back in the stats view.
- [x] 3.2 `TaskListComponent`: `project` input that scopes the list, defaults quick-add creations to
      that project, and refreshes when a task is created through the shared drawer.

## 4. Frontend — create into the project
- [x] 4.1 `TaskDrawerService.openDrawer(preset?)`: carry an optional `{ project }` preset.
- [x] 4.2 `TaskCreateDrawerComponent`: seed the draft from the preset each time it opens.

## 5. Frontend — project detail view
- [x] 5.1 Rebuild `project-detail.component.*`: header (title, Markdown description, dates, tags),
      Edit + New Task actions, and the project's task list below; handle loading / not-found.
- [x] 5.2 Style it from the `--org-*` design tokens.

## 6. Frontend — project form
- [x] 6.1 Update an existing project (PUT) instead of always creating; drop the bogus start-date
      override; convert dates between the API format and the datepicker so an edit saves.

## 7. Verification
- [x] 7.1 `uv run python manage.py test` (127 tests) and `uv run ruff check .`
- [x] 7.2 `npm test` (116 tests) and `npm run build` in `frontend/`
