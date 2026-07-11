# Tasks: Richer task list rows and detail view

## 1. Backend — read serializers
- [x] 1.1 `TaskSerializer`: add read-only `created_date`, a read-only `parent_task_title`
      (source: `parent_task.title`), and read-only `template` + `template_title`.
- [x] 1.2 `TaskListSerializer`: add read-only `template` + `template_title` (priority, status,
      `end_date`, and `project` are already returned).

## 2. Backend — comments
- [x] 2.1 `TaskCommentSerializer`: add writable `task`; make `user` read-only and add a read-only
      `user_username` for display.
- [x] 2.2 `TaskCommentViewSet`: `get_queryset` scoped to comments on the request user's tasks;
      `perform_create` sets `user=self.request.user`; keep `IsAuthenticated`.
- [x] 2.3 Tests: create a comment (author derived, associated to task), owner-scoping hides another
      user's comments, task serializer exposes the new fields.

## 3. Frontend — model + service
- [x] 3.1 `task.ts`: add `created_date` (present), `parent_task_title?`, `template?`,
      `template_title?`, and a `comments?: TaskComment[]`; add a `TaskComment` interface.
- [x] 3.2 `task.service.ts`: `addComment(taskId, description)` POSTing to `/api/comments/`.

## 4. Frontend — task list
- [x] 4.1 Render on each row: priority accent + flag, status badge (not for "idea"), deadline
      (overdue/soon emphasis), project chip, and the recurring badge when `template` is set.
- [x] 4.2 Helpers for priority/status label + class, overdue/soon detection, project-name lookup
      (`tasks/task-meta.ts`).
- [x] 4.3 Adjust row height/CSS so the added meta line fits the fixed-height virtual rows.

## 5. Frontend — task detail
- [x] 5.1 Comments section: list existing comments (author + timestamp) and an add-comment form.
- [x] 5.2 Read-only metadata footer (created / last changed / completed).
- [x] 5.3 Parent-task link (when `parent_task` set) and recurring badge (when `template` set).

## 6. Verify
- [x] 6.1 `uv run python manage.py test tasks` — new comment/serializer tests pass. (The 7 failing
      `test_templates_api` tests are pre-existing: the `/api/template/` viewset/route from
      `add-recurring-tasks` is not implemented yet — unrelated to this change.)
- [x] 6.2 `uv run ruff check .` and `ruff format` clean on the changed files.
- [x] 6.3 `cd frontend && npm run build` passes (full AOT template type-check). NOTE: `npm test`
      (vitest) deadlocks at the esbuild worker level in this environment — a runner/infra issue, not
      a code failure.
- [x] 6.4 `openspec validate enrich-task-ui --strict` passes.
