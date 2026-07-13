# Tasks

## 1. Foundations
- [x] 1.1 Expose `taskAt(index)` on `TaskDataSource` so the list can resolve the highlighted row.
- [x] 1.2 Expose a `focus()` method on `TaskQuickAddComponent`.

## 2. Shortcuts help panel
- [x] 2.1 Add a reusable `KeyboardShortcutsComponent` (shared): modal overlay + scrim, `open` model,
      grouped `<kbd>` rows, closes on Escape / backdrop / close button, styled from `--org-*` tokens.

## 3. Task-list keyboard handling
- [x] 3.1 Track a `highlighted` index signal; render the active row with a visible highlight and
      keep it in sync when rows are removed (delete / filtered out).
- [x] 3.2 Handle `ArrowDown` / `ArrowUp` navigation, clamped, scrolling the row into view in the
      virtual-scroll viewport.
- [x] 3.3 Handle `Enter` (toggle done), `e` (edit), `Delete` (delete), `t` (toggle today) on the
      highlighted row.
- [x] 3.4 Handle `/` (focus search) and `c` (focus quick-add).
- [x] 3.5 Handle `Ctrl+1` / `Ctrl+2` / `Ctrl+3` filter toggles.
- [x] 3.6 Handle `?` (open panel) and `Escape` (close panel / blur field / clear highlight); ignore
      single-letter shortcuts while a text field has focus.
- [x] 3.9 Harden the typing guard so typing always wins: match any editable element (`input`,
      `textarea`, `select`, contenteditable — via `closest`, so a caret in a descendant counts) on
      both the event target and `document.activeElement`, and suppress the bare-key shortcuts
      entirely while a modal is open over the list (the app-wide create-task drawer, whose buttons
      could otherwise take focus while `Enter`/`e`/`Delete` still hit the list behind it). The guard
      sits immediately before the key switch, so shortcuts added later are covered by construction.
- [x] 3.7 Add the toolbar keyboard button that opens the panel.
- [x] 3.8 Highlight the row on click so mouse and keyboard share one cursor.

## 4. Bug fix surfaced while verifying
- [x] 4.1 Fix the write/refetch race in `toggleTaskDone` / `toggleTaskToday` / `deleteTask`: the row
      update was applied while the PATCH/DELETE was still in flight, so `removeById`'s revalidating
      refetch could read the task back in its pre-toggle state and re-insert the row (and leave the
      header count one too high). The list is now updated once the write has landed. Pre-existing —
      reachable from the on-row buttons too — but `Enter` hit it every time.
- [x] 4.2 Clamp the highlight reactively off `totalCount`, since the count now settles asynchronously.

## 5. Tests & validation
- [x] 5.1 Unit tests for the key handling (navigation, actions, typing guard, filter toggles, panel).
      The typing tests fire *every* bare shortcut at each kind of field, so a new shortcut that
      forgets the guard fails them.
- [x] 5.2 `npm test` (73 passed) and `npm run build` pass.
- [x] 5.3 End-to-end verification in a real browser against the API (22/22 shortcut checks:
      navigation, virtual-scroll follow, all four row actions confirmed against the API,
      focus/filter shortcuts, panel open/close), plus 13/13 typing-guard checks: text containing
      every shortcut key typed character-by-character into the search, quick-add, drawer title, and
      drawer description fields, with the drawer's non-field focus case covered.
- [x] 5.4 `openspec validate add-task-list-keyboard-shortcuts --strict` passes.
