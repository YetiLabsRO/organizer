## 1. Backend — pagination, scoping, payload
- [x] 1.1 Add `tasks/pagination.py` with `TaskLimitOffsetPagination` (`default_limit=50`, `max_limit=200`)
- [x] 1.2 Wire `pagination_class` on `TaskItemViewSet` (endpoint-scoped, not global)
- [x] 1.3 Scope `get_queryset` to `owner=self.request.user`; set `owner` in `perform_create`
- [x] 1.4 Add `TaskListSerializer` (no nested `comments`); return it for the `list` action; make `owner` read-only
- [x] 1.5 Append `pk` tiebreaker to `TaskItem.Meta.ordering`; `makemigrations tasks`
- [x] 1.6 Add `today_view` OR-filter to `TaskFilterSet` (`for_today=true` OR completed today)
- [x] 1.7 Fix latent `comments` bug (`related_name="comments"` on `TaskComment.task`); migration
- [x] 1.8 Add `tasks/tests.py` (envelope, scoping, owner-on-create, list-omits-comments, today_view); `manage.py test` green; `ruff check` clean

## 2. Frontend — data layer
- [x] 2.1 Add `page.ts` with the `Page<T>` envelope interface
- [x] 2.2 `TaskService`: paginated `getTasksPage(filters, offset, limit): Observable<Page<Task>>`
- [x] 2.3 `TaskFilters`: emit `today_view` query param (limit/offset appended by the service per window)
- [x] 2.4 Add `TaskDataSource extends DataSource<Task | undefined>` (windowed range-fetch + buffer, sparse cache)

## 3. Frontend — task list UI
- [x] 3.1 Rewrite `task-list.component.ts` to own a `TaskDataSource` signal; reset on filter/search change
- [x] 3.2 Rewrite template with `<cdk-virtual-scroll-viewport>` + `*cdkVirtualFor`, skeleton placeholders
- [x] 3.3 Add debounced, server-side free-text search that drives the window
- [x] 3.4 Reconcile add/delete/toggle mutations with the windowed source
- [x] 3.5 Compact fixed-height, responsive rows (title + clamped description + tags + tap-friendly toolbar)

## 4. Frontend — shell & look
- [x] 4.1 Rebuild `app.component.html` header as a collapsing Bootstrap 5.3 navbar (remove stray doctype/html/body)
- [x] 4.2 Task-list styles: viewport height, skeleton, row/tag styling, mobile breakpoints
- [x] 4.3 `npm run build` green; `npm test` smoke suite green (27/27 on warm run)

## 5. Sync
- [x] 5.1 Tick this checklist; `openspec validate add-task-pagination-and-responsive-list --strict`
