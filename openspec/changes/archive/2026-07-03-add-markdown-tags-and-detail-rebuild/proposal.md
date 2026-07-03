# Change: Markdown, inline tag/project autocomplete, and a rebuilt task detail

## Why
The task UI has grown rough: tags are tiny and unclickable, the task title floats mid-row, quick-add
uses an awkward `@tags(...)` syntax, descriptions are raw text, and the task detail screen duplicates
the tag list, hides most fields, and offers a bare textarea. This change makes tags first-class,
adds Markdown throughout, and rebuilds the detail screen.

## What Changes
- **Task list**
  - Bigger, readable tag pills; **clicking a tag pill filters the list by that tag**.
  - Task title **top-aligned**, aligned with the checkbox column.
  - Task description **rendered as Markdown** in the row (clamped), not raw text.
- **Quick-add** — replace `@tags(work, urgent)` with inline **`#tagname`** tokens and **`@projectname`**
  for the project, both with an **autocomplete dropdown** (tags shown in their colors) while typing.
- **Task detail/edit (rebuilt from scratch, full-page route)**
  - **All** task fields editable: title, status, priority, start/end/completed dates, estimated time,
    daily-focus, **project**, **tags**.
  - **Single seamless tag editor** (colored, removable chips + `#` autocomplete) — no more duplicated
    tag list beside the input.
  - Description edited as **Markdown with a live preview pane**.
- **Tags** — tag `description` supports **Markdown** (stored as free text / `TextField`) and is
  rendered as Markdown in the tag detail view.
- **Shared building blocks** — a small `marked`-based Markdown renderer and a CDK-Overlay–based
  mention autocomplete (`#` tags / `@` projects); no fragile third-party mention/markdown Angular deps.

## Impact
- Affected specs: `web-frontend`, `tag-management`
- Affected code:
  - Backend: `tasks/models.py` (Tag.description → TextField) + migration
  - Frontend (new): `shared/markdown/*`, `shared/mention-autocomplete/*`
  - Frontend (changed): `tasks/task-list/*`, `tasks/task-detail/*`, `tags/tag-detail/*`,
    `tasks/task.service.ts`/`task.ts`, `projects/project.service.ts`, `package.json` (+`marked`)
- New dependency: `marked` (Markdown → HTML; output sanitized via Angular's `[innerHTML]`).
