## Context
Production holds tens of thousands of tasks. The current `/api/task/` returns the whole queryset as
a bare JSON array and the Angular list renders every row via `@for`, holding all data and DOM nodes
at once. We need server-side pagination plus client-side windowing (render + fetch only what's near
the viewport), and a mobile-friendly restyle. The frontend is already Angular 21 standalone with
signals and `@angular/cdk` 21 installed; Bootstrap 5.3.3 is the CSS framework.

## Goals / Non-Goals
- Goals: constant-ish memory/DOM regardless of task count; only fetch pages near the viewport;
  preserve existing filters, quick-add, and toggles; owner-scoped tasks; responsive layout.
- Non-Goals: paginating tag/project/comment endpoints (small sets; the tag cache relies on plain
  arrays); introducing a new UI framework; changing the detail/edit views beyond what pagination
  requires.

## Decisions
- **LimitOffsetPagination, task endpoint only.** Offset/limit maps 1:1 onto a virtual-scroll range
  fetch. Applied via `pagination_class` on `TaskItemViewSet` (not a global
  `DEFAULT_PAGINATION_CLASS`) so tag/project/comment consumers and the tag cache keep receiving
  arrays. `default_limit=50`, `max_limit=200`.
- **Deterministic ordering.** Append `pk` to `TaskItem.Meta.ordering`; without a unique final key,
  limit/offset pages can duplicate or drop rows across requests.
- **List vs detail serializer.** `TaskListSerializer` drops the nested `comments` (not rendered in
  the list); `TaskItemViewSet.get_serializer_class` returns it for `action == "list"` and the full
  `TaskSerializer` otherwise. Detail/create/update keep comments.
- **Owner scoping.** `get_queryset` filters by `owner=self.request.user`; `perform_create` stamps
  `owner`. `owner` becomes read-only in the serializer so clients can't spoof it. Existing `owner`
  query-param filter is unaffected (it further narrows the already-scoped set).
- **`today_view` OR-filter.** Replaces the client's two-call "today + completed" hack with one
  paginable query: `Q(for_today=True) | Q(completed_date__date=today)`.
- **Windowed DataSource (frontend).** A `TaskDataSource extends DataSource<Task | undefined>` keeps a
  sparse array sized to `count`. On `connect` it subscribes to the viewport's `viewChange` range and
  fetches the pages covering `[start, end]` plus a one-page buffer each side; fetched pages are
  tracked so each loads once. Not-yet-loaded slots are `undefined` and render as skeleton rows.
- **Reset on filter/search change.** Changing filters or the search term creates a fresh
  `TaskDataSource`, held in a signal, so the viewport re-connects from the top with clean state.
  Mutations (add/delete/toggle) update the current source's cache optimistically and, when they
  change membership, trigger a reset.
- **`*cdkVirtualFor`, not `@for`.** CDK virtualization has no built-in-control-flow equivalent; the
  list uses the `*cdkVirtualFor` structural directive inside `<cdk-virtual-scroll-viewport>`. This
  is the one sanctioned exception to the "use `@if`/`@for`" convention; `@if`/`@for` are still used
  for row internals (skeleton vs content, tag badges). Documented so it isn't read as a regression.
- **Fixed-height rows.** CDK's default fixed-size strategy needs a known item height, and uniform
  rows scan best for huge lists. Rows are a single fixed height with title + one-line clamped
  description + tags; the viewport fills the available height and scrolls internally.

## Risks / Trade-offs
- **Response-shape break.** Any consumer expecting an array from `/api/task/` breaks. Mitigation: the
  only list consumer is `TaskService.getTasks`, updated in this change; detail uses `/api/task/:id`
  (unpaginated). Grep confirms no other callers.
- **Owner scoping hides pre-existing tasks** whose `owner` differs/`NULL`. This is the intended
  product behavior (personal organizer) and the user's explicit choice.
- **Fixed row height clamps long descriptions** in the list; full text remains on the detail view.
- **`viewChange` fires often;** fetches are de-duped via a fetched-pages set so scrolling doesn't
  re-request pages.

## Migration Plan
- `makemigrations tasks` emits an `AlterModelOptions` (ordering) migration — no data migration.
- Deploy backend and frontend together (response-shape break). No rollback data concerns; reverting
  both restores prior behavior.

## Open Questions
- None blocking. Page size (50) and buffer (1 page) are tunable constants.
