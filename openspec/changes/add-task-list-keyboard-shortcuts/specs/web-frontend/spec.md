# web-frontend Spec Delta

## ADDED Requirements

### Requirement: Task list keyboard navigation
The task list SHALL maintain a single highlighted row that can be moved with the arrow keys. The
highlight SHALL be visually distinct, SHALL be clamped to the bounds of the list, and SHALL be
scrolled into view as it moves, including into parts of the list that have not yet been fetched.
Clicking a row SHALL highlight it, so pointer and keyboard share one cursor.

#### Scenario: Move the highlight with the arrow keys
- **WHEN** a user presses `ArrowDown` (or `ArrowUp`) on the task list
- **THEN** the highlight moves to the next (or previous) task and that row is scrolled into view

#### Scenario: Highlight stops at the ends of the list
- **WHEN** the highlight is on the first task and the user presses `ArrowUp` (or on the last task and
  presses `ArrowDown`)
- **THEN** the highlight stays where it is

#### Scenario: Clicking a row highlights it
- **WHEN** a user clicks anywhere on a task row
- **THEN** that row becomes the highlighted row and subsequent shortcuts act on it

### Requirement: Task list keyboard actions
The task list SHALL act on the highlighted task in response to single-key shortcuts: `Enter` toggles
the task between completed and not completed, `e` opens the task's edit view, `Delete` deletes the
task, and `t` toggles the task's daily-focus ("today") flag. Each action SHALL behave exactly as the
equivalent on-row control, and SHALL do nothing when no row is highlighted.

#### Scenario: Toggle completion from the keyboard
- **WHEN** a task is highlighted and the user presses `Enter`
- **THEN** the task is marked completed if it was not, or not completed if it was

#### Scenario: Edit the highlighted task
- **WHEN** a task is highlighted and the user presses `e`
- **THEN** the app navigates to that task's detail/edit view

#### Scenario: Delete the highlighted task
- **WHEN** a task is highlighted and the user presses `Delete`
- **THEN** the task is deleted and removed from the list

#### Scenario: Toggle today from the keyboard
- **WHEN** a task is highlighted and the user presses `t`
- **THEN** the task's daily-focus flag is toggled

### Requirement: Task list focus and filter shortcuts
The task list SHALL provide shortcuts that move focus and drive the filter toggles: `/` focuses the
search field, `c` focuses the quick-add field, and `Ctrl+1`, `Ctrl+2`, and `Ctrl+3` toggle the Todo,
Completed, and Today filters respectively.

#### Scenario: Jump to search
- **WHEN** a user presses `/` on the task list
- **THEN** the search field receives focus and no `/` character is typed into it

#### Scenario: Jump to quick-add
- **WHEN** a user presses `c` on the task list
- **THEN** the quick-add field receives focus and no `c` character is typed into it

#### Scenario: Toggle a filter
- **WHEN** a user presses `Ctrl+1` (or `Ctrl+2`, or `Ctrl+3`)
- **THEN** the Todo (or Completed, or Today) filter toggles and the list reloads, exactly as if the
  corresponding button had been clicked

### Requirement: Typing always wins over the shortcuts
Every unmodified single-key shortcut on the task list SHALL be inert whenever the user is typing, so
that arbitrary text can always be written. "Typing" means focus is in any element that accepts typed
characters — an `input`, `textarea`, `select`, or contenteditable region (including a caret in one of
its descendants) — anywhere on the page, whether that field belongs to the list or to a component
mounted over it, such as the app-wide create-task drawer. While a modal is open over the list (the
create-task drawer or the shortcuts panel), the list SHALL ignore its single-key shortcuts entirely,
including keys pressed while focus rests on a non-field element such as a button. Modifier-based
shortcuts (`Ctrl+1/2/3`) MAY still run while typing, since they produce no text. `Escape` SHALL
return focus out of the field, after which the shortcuts resume.

#### Scenario: Typing is never intercepted
- **WHEN** focus is in the search, quick-add, or drawer field and the user types text containing
  `c`, `e`, `t`, `/`, or `?`
- **THEN** every character is entered into the field and no shortcut runs

#### Scenario: A modal over the list swallows the shortcuts
- **WHEN** the create-task drawer is open and a key such as `e`, `Enter`, or `Delete` is pressed
  while focus rests on one of its buttons rather than a text field
- **THEN** the task list behind it does not navigate, complete, or delete anything

#### Scenario: Modifier shortcuts still work while typing
- **WHEN** focus is in the search field and the user presses `Ctrl+2`
- **THEN** the Completed filter toggles and focus stays in the field

#### Scenario: Escape returns to the list
- **WHEN** focus is in a text field and the user presses `Escape`
- **THEN** focus leaves the field and the single-key shortcuts work again

### Requirement: Keyboard shortcuts help panel
The task list SHALL offer a help panel listing every available shortcut with its keys and what it
does. The panel SHALL open on `?` and from a visible control in the list toolbar, and SHALL be
dismissible with `Escape`, the close button, or a click outside it.

#### Scenario: Open the shortcuts panel
- **WHEN** a user presses `?` on the task list
- **THEN** a panel opens listing every shortcut and its action

#### Scenario: Dismiss the shortcuts panel
- **WHEN** the shortcuts panel is open and the user presses `Escape`
- **THEN** the panel closes and the list resumes handling shortcuts
