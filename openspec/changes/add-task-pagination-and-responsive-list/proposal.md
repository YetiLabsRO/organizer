# Change: Paginated, windowed task list with a mobile-first refresh

## Why
The task list loads the **entire** `/api/task/` queryset in one request and renders every row —
unworkable at the tens-of-thousands scale production now holds. The endpoint also returns every
user's tasks (no owner scoping) with full nested comments on each row, and the list UI uses a rigid
12-column grid that does not reflow on phones.

## What Changes
- **BREAKING (API response shape):** `GET /api/task/` returns a DRF limit/offset pagination envelope
  `{count, next, previous, results}` instead of a bare array. Only the task endpoint changes;
  tag/project/comment endpoints keep returning arrays.
- Scope the task list to the authenticated owner; set `owner` on create so new tasks belong to the
  creator.
- Split the task serializer: the **list** view omits nested `comments` (kept on the detail view) to
  shrink the per-row payload.
- Fix a latent bug: `TaskComment.task` had no `related_name`, so the `comments` field (being
  read-only/not-required) was silently skipped and task detail never actually returned comments. Add
  `related_name="comments"` so the detail view genuinely includes them.
- Add a deterministic `pk` tiebreaker to task ordering so pages are stable.
- Add a `today_view` OR-filter (`for_today=true` OR completed today) so the "today + completed" view
  is a single paginable query instead of two merged client calls.
- Frontend: render the list with a CDK virtual-scroll viewport backed by a **windowed data source**
  that fetches only the pages covering the visible range plus a buffer on each side, with skeleton
  placeholders for not-yet-loaded rows.
- Frontend: server-side, debounced free-text search drives the same paginated window.
- Frontend: refresh the look for mobile — a collapsing Bootstrap 5.3 navbar and compact,
  fixed-height task rows that reflow on small screens.

## Impact
- Affected specs: `task-management`, `web-frontend`
- Affected code:
  - Backend: `organizer/settings.py`, `tasks/views.py`, `tasks/pagination.py` (new),
    `tasks/api/serializers.py`, `tasks/filters.py`, `tasks/models.py` (+ migration)
  - Frontend: `tasks/task.service.ts`, `tasks/task-filters.ts`, `tasks/task-data-source.ts` (new),
    `page.ts` (new), `tasks/task-list/*`, `app.component.html`, `styles.css`
