# Change: Richer task list rows and detail view

## Why
The task list only shows a title, description, tags, and actions — even though every task also
carries a **priority**, **status**, **deadline**, and **project**, and the list API already returns
all of them. Users have to open each task to see whether it's high priority, blocked, overdue, or
which project it belongs to. Likewise the detail/edit view exposes the editable fields but hides
information the model already holds: a task's **comments** (returned by the API but never rendered),
its **created/changed/completed metadata**, and its **parent task**. This change surfaces that
existing data so the list and detail views are usable at a glance.

## What Changes
- **Task list rows** SHALL show, in addition to today's title/description/tags:
  - a **priority** indication (a coloured left accent + a flag for high/low; neutral priority is
    unmarked),
  - the **status** as a small badge (hidden for the default "Idea" so the list stays quiet),
  - the **deadline** (`end_date`), emphasised when overdue or due soon,
  - the owning **project** as a subtle chip.
- **Task detail view** SHALL additionally show:
  - a **comments** section that lists existing comments (author + timestamp) and lets the user add
    a new one,
  - a read-only **metadata** footer (created, last changed, completed dates),
  - a link to the **parent task** when the task has one.
- **Status & priority controls** on the detail view are upgraded from plain dropdowns:
  - **status** becomes a **DAG-style flow** — `Idea → In progress → Done`, with `Blocked` and
    `Given up` branching off `In progress` — where each state is a clickable node,
  - **completion** stays the satisfying **checkbox** (the terminal `Done` node), keeping its toggle
    interaction,
  - **priority** becomes a **segmented control** with a traffic-light + magnitude-bar treatment
    (Low / Normal / High).
- **Backend (read side):** expose `created_date`, `parent_task` title, and the recurring `template`
  on the task serializers so the detail view can render metadata, the parent link, and the recurring
  badge (the recurring badge itself is owned by the in-flight `add-recurring-tasks` change; its
  serializer/UI checklist items are completed here since they share this code).
- **Backend (comments):** make `/api/comments/` usable and safe for the UI — accept the `task` on
  create, derive the **author from the authenticated user** (clients no longer supply `user`), and
  **owner-scope** the endpoint so a user only ever sees/comments on their own tasks (today it returns
  every user's comments).

Non-goals: no changes to filtering, quick-add, the recurrence rule/editor, or task write semantics
beyond comments.

## Impact
- Affected specs:
  - **web-frontend** (MODIFIED): richer task-list rows; detail view shows comments, metadata, and a
    parent-task link.
  - **task-comments** (MODIFIED): author derived from the authenticated user; endpoint owner-scoped.
- Affected code:
  - `tasks/api/serializers.py` — task metadata/template/parent-title read fields; `TaskCommentSerializer`
    `task` write field + server-set author.
  - `tasks/views.py` — owner-scope `TaskCommentViewSet` and set the author in `perform_create`.
  - `tasks/test_*` — comment create/scoping + task serializer field tests.
  - `frontend/src/app/tasks/task.ts`, `task.service.ts` — model fields, comment model, add-comment call.
  - `frontend/src/app/tasks/task-list/*` — render priority/status/deadline/project (+ recurring badge).
  - `frontend/src/app/tasks/task-detail/*` — comments, metadata footer, parent link (+ recurring badge).
