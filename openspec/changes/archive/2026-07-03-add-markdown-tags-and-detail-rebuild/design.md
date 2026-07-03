## Context
Angular 21 standalone app, Bootstrap 5.3, `@angular/cdk` 21, ngx-chips (currently used for the
detail tag input), ngx-color-picker. No Markdown or mention/autocomplete library is installed, and
no third-party Angular mention library has a confirmed Angular-21 build. Task/tag/project services
already resolve related tags client-side from a cached list.

## Goals / Non-Goals
- Goals: readable/clickable tags; Markdown for task and tag descriptions (list + detail); inline
  `#tag` / `@project` autocomplete for quick-add and the detail tag editor; a rebuilt, complete
  task detail/edit page; no fragile new dependencies.
- Non-Goals: a rich WYSIWYG editor; changing the REST payloads beyond Tag.description's column type;
  reworking project/tag list pages beyond Markdown rendering of tag descriptions.

## Decisions
- **Markdown via `marked` + Angular sanitizer.** A standalone `MarkdownComponent`
  (`<div [innerHTML]="html()">`) runs `marked.parse(value)` and binds through `[innerHTML]`, which
  Angular's DomSanitizer scrubs (scripts/handlers stripped) — no `bypassSecurityTrust*`, no DOMPurify.
  Chosen over `ngx-markdown` to avoid an Angular-version-locked wrapper on a brand-new Angular.
- **Mention autocomplete (custom).** The active `#…`/`@…` token is found by regex on the input value
  + caret index; matches come from `TagService.searchTags` / cached `ProjectService.getProjects`,
  rendered in a presentational `SuggestionListComponent` (tag colors, keyboard nav) inserted on
  select as the canonical `#slug`/`@slug`. Chosen over `angular-mentions` (no confirmed Angular-21
  support → build risk).
  - **Refinement vs. the plan:** the dropdown is positioned with plain CSS (`position:absolute`
    under the field, inside a `position:relative` wrapper) rather than CDK Overlay. The fields aren't
    inside overflow-clipping containers, so this is simpler and avoids overlay/portal wiring while
    delivering the same input-anchored UX. Still fully custom, no third-party mention lib.
- **Token model for quick-add.** On submit, the raw text is parsed: `#slug` tokens → tag ids (resolved
  via `TagService`), a single `@slug` → project id; both stripped from the resulting title. Preserves
  today's "type a task, tag it inline" flow with the new syntax.
- **Detail = full-page route** (`/tasks/:id`, deep-linkable). Rebuilt with a Reactive/`ngModel` form
  exposing every field. Tags use one **chip editor** (colored removable chips + a `#`-autocomplete
  add-field) — the duplicated static badge row is deleted. Project uses `@`-autocomplete (single).
  Description is a two-pane Markdown editor (textarea + live `MarkdownComponent` preview).
- **Markdown in the list.** The row description renders through `MarkdownComponent`, clamped to one
  line (CSS `line-clamp`) so fixed-height virtual-scroll rows are preserved; block elements render
  inline-ish and are ellipsised.
- **Project name resolution.** The list/detail resolve `project` id → title from a cached project
  list (mirroring how tags are resolved), so no serializer change is needed for display.
- **Tag pill click → filter.** In the list, clicking a pill sets the active tag filter (single tag)
  and rebuilds the windowed data source; an active-tag chip with a clear affordance is shown.

## Risks / Trade-offs
- **CDK caret anchoring.** Anchoring the dropdown to the input (not the exact caret) is simpler and
  robust; slight UX compromise (dropdown not glued to the caret) accepted.
- **Markdown in a clamped row.** Multi-block Markdown in one clamped line can look terse; acceptable —
  full render is on the detail page.
- **`marked` sanitization.** Relying on Angular's `[innerHTML]` sanitizer (not raw HTML passthrough)
  keeps it XSS-safe; links get `rel="noopener"` via a marked renderer tweak.
- **ngx-chips.** The rebuilt detail no longer needs ngx-chips for tags (replaced by the chip editor);
  leave the dependency in place unless nothing else uses it (verify before removing).

## Migration Plan
- `Tag.description` CharField(1024) → `TextField(blank/null)` — a widening `AlterField` migration; no
  data transformation, no data loss.
- Frontend-only otherwise; ship behind the same deploy. `marked` added to `package.json`.

## Open Questions
- None blocking. Autocomplete could later be extended to `#`/`@` inside the description; out of scope now.
