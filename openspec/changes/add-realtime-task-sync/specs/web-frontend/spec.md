## ADDED Requirements

### Requirement: Live-updating task views

The SPA SHALL keep its task views in sync with the server in real time. While a task view is open, a
change to a task made anywhere else — another browser, the phone, an MCP client, or the recurring-task
job — SHALL be reflected without a manual reload.

#### Scenario: Change in another browser appears

- **WHEN** the task list is open in one browser
- **AND** the same user completes a task in another browser
- **THEN** the first browser reflects the completion without being reloaded

#### Scenario: Task created elsewhere appears in the list

- **WHEN** the task list is open
- **AND** a task matching the active filters is created elsewhere
- **THEN** the list shows it

#### Scenario: Task deleted elsewhere disappears

- **WHEN** the task list is open
- **AND** one of its visible tasks is deleted elsewhere
- **THEN** the row is removed from the list

#### Scenario: The focus view stays live too

- **WHEN** the priority focus view is open
- **AND** a task changes elsewhere
- **THEN** the affected priority band updates

#### Scenario: Filters are respected

- **WHEN** a live update makes a visible task no longer match the active filters
- **THEN** it is removed from the view

### Requirement: Task event socket lifecycle

The SPA SHALL open its task-event socket only while the user is authenticated, and SHALL survive
transient network loss.

#### Scenario: Socket opens on login and closes on logout

- **WHEN** the user logs in
- **THEN** the SPA opens the task-event socket and authenticates it with the stored token
- **WHEN** the user logs out
- **THEN** the SPA closes the socket

#### Scenario: Dropped connection reconnects

- **WHEN** the socket drops because the network went away
- **THEN** the SPA reconnects with exponential backoff
- **AND** refreshes the open task view once reconnected, so changes missed while offline appear

#### Scenario: Rejected credentials do not retry in a loop

- **WHEN** the server closes the socket with code `4401`
- **THEN** the SPA stops reconnecting until the user authenticates again

#### Scenario: Live sync is not required for the app to work

- **WHEN** the socket cannot connect at all
- **THEN** every existing view still loads and every task action still works over the REST API

### Requirement: Stale events are ignored

The SPA SHALL apply an incoming event to a task only when it is newer than the state already held for
that task, comparing the task's `changed_date`.

#### Scenario: Out-of-order event is dropped

- **WHEN** an event arrives for a task whose `changed_date` is not newer than the one already
  rendered
- **THEN** the SPA ignores it, leaving the newer state on screen
