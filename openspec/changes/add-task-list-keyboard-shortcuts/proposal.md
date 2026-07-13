# Change: Keyboard shortcuts on the task list

## Why
The task list is the screen users spend the most time on, and every action on it — searching,
adding, completing, editing, deleting, flagging for today, switching the Todo/Completed/Today
filters — currently requires reaching for the mouse. With a list that routinely runs to four
figures, that round-trip is the single biggest friction in the app. A keyboard-driven list lets a
user triage a backlog without leaving the home row.

## What Changes
- **Row highlight + navigation.** The task list SHALL maintain a *highlighted* row. `ArrowDown` /
  `ArrowUp` move the highlight through the list (clamped at both ends) and scroll it into view,
  working with the virtualised viewport so it also drives loading of not-yet-fetched pages.
  Clicking a row highlights it, so mouse and keyboard share one cursor.
- **Actions on the highlighted row:**
  - `Enter` — toggle completed / not completed,
  - `e` — open the task's edit (detail) view,
  - `Delete` — delete the task,
  - `t` — toggle the task's "today" flag.
- **Focus shortcuts:** `/` focuses the search box, `c` focuses the quick-add input.
- **Filter shortcuts:** `Ctrl+1` toggles the *Todo* filter, `Ctrl+2` *Completed*, `Ctrl+3` *Today* —
  the same three toggles as the button group.
- **Help panel:** `?` opens a panel listing every shortcut; `Escape` (or the backdrop / close
  button) dismisses it. A small keyboard button in the toolbar opens the same panel so the feature
  is discoverable without knowing the shortcut.
- **Typing is never hijacked.** While focus is in a text field, single-letter shortcuts are inert
  (so `c`, `e`, `t` type normally); `Escape` blurs the field. The modifier-based filter shortcuts
  still work anywhere, since they emit no text.

Non-goals: no shortcuts on the Focus / stats / detail screens, no rebinding UI, no multi-select or
bulk operations, no changes to the API.

## Impact
- Affected specs:
  - **web-frontend** (MODIFIED): task list gains keyboard navigation, row actions, focus/filter
    shortcuts, and a shortcuts help panel.
- Affected code:
  - `frontend/src/app/tasks/task-list/*` — key handling, highlighted-row state + styling, panel wiring.
  - `frontend/src/app/tasks/task-data-source.ts` — expose the task at an index for the highlight.
  - `frontend/src/app/tasks/task-quick-add/task-quick-add.component.ts` — expose `focus()`.
  - `frontend/src/app/shared/keyboard-shortcuts/*` — new reusable shortcuts help panel.
