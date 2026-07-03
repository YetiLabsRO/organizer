## 1. Backend
- [x] 1.1 `Tag.description` CharField(1024) → `TextField(null=True, blank=True)`; `makemigrations` (0008)
- [x] 1.2 Confirm tag/task/project serializers still round-trip; `manage.py test` (9 pass); `ruff check`

## 2. Frontend — shared building blocks
- [x] 2.1 Add `marked` to `package.json`; `npm install`
- [x] 2.2 `shared/markdown/markdown.component.ts` — standalone, `marked.parse` → `[innerHTML]` (sanitized); inline mode for the list
- [x] 2.3 `shared/autocomplete/suggestion-list.component.ts` + inline `#`/`@` autocomplete in quick-add/chips/picker (CSS-anchored dropdown, keyboard nav, colored tags)
- [x] 2.4 `ProjectService.getProjectsCached()` (id → title / `@` autocomplete); `shared/tag-color.util.ts`

## 3. Task list
- [x] 3.1 Bigger tag pills; task title top-aligned with the checkbox column (rows `align-items-start`)
- [x] 3.2 Clicking a tag pill sets the active tag filter and rebuilds the window; active-tag chip with clear
- [x] 3.3 Render row description via `MarkdownComponent` (inline, clamped to one line)
- [x] 3.4 Quick-add component: `#tag`/`@project` + autocomplete; parse+strip tokens on submit (replaces `@tags(...)`)

## 4. Task detail (full-page rebuild)
- [x] 4.1 New form with every field: title, status, priority, start/end dates, estimated_time, for_today, project, tags, description
- [x] 4.2 Single seamless tag editor (`TagChipsInputComponent` — colored removable chips + `#` autocomplete); duplicated badge row removed
- [x] 4.3 Project via `ProjectPickerComponent` (`@`/type-to-filter single-select)
- [x] 4.4 Markdown description editor with live preview pane (side-by-side on desktop, Write/Preview toggle on mobile)
- [x] 4.5 Save / toggle-complete / delete wired to `TaskService`

## 5. Tag detail
- [x] 5.1 Edit tag `description` as Markdown with live preview; render Markdown in read mode

## 6. Verify
- [x] 6.1 `npm run build` (green); `npm test` smoke (27/27)
- [x] 6.2 Backend `manage.py test` (9) + `ruff` green
- [x] 6.3 Tick this checklist; `openspec validate add-markdown-tags-and-detail-rebuild --strict`
