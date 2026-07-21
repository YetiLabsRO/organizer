## ADDED Requirements

### Requirement: Task events WebSocket endpoint

The system SHALL expose a WebSocket endpoint at `/ws/tasks/` that streams task-change events for the
authenticated user. The endpoint SHALL be served by the ASGI application alongside the existing REST
API and MCP endpoint.

#### Scenario: Client connects and receives events

- **WHEN** an authenticated client holds an open socket to `/ws/tasks/`
- **AND** a task owned by that user is created, updated, or deleted by any writer
- **THEN** the server sends the client a corresponding event within one second

#### Scenario: WebSocket scopes are routed away from the MCP app and Django

- **WHEN** an ASGI `websocket` scope arrives for a path under `/ws/`
- **THEN** it is dispatched to the WebSocket router
- **AND** `websocket` scopes for `/mcp` continue to reach the MCP app
- **AND** the `lifespan` scope remains owned by the MCP app

### Requirement: First-message socket authentication

Because a browser cannot set an `Authorization` header on a WebSocket handshake, the server SHALL
authenticate the socket from its first message rather than from the handshake, and SHALL NOT accept a
credential passed in the URL.

#### Scenario: Valid token authenticates the socket

- **WHEN** a client sends `{"type": "auth", "token": "<valid DRF token>"}` as its first message
- **THEN** the server resolves the token to its user, subscribes the socket to that user's task
  events, and replies with `{"type": "auth.ok"}`

#### Scenario: Invalid token is rejected

- **WHEN** a client's first message carries a token that matches no user
- **THEN** the server closes the socket with code `4401` and sends no task events

#### Scenario: Silent client is disconnected

- **WHEN** a client does not send an auth message within the grace period
- **THEN** the server closes the socket with code `4401`

#### Scenario: No events before authentication

- **WHEN** a socket is open but has not authenticated
- **THEN** the server sends it no task events, regardless of what changes on the server

### Requirement: Owner-scoped event delivery

Task events SHALL be delivered only to sockets authenticated as the task's owner. A task whose owner
is null SHALL NOT be broadcast.

#### Scenario: Events are not leaked across users

- **WHEN** user A and user B each hold an authenticated socket
- **AND** a task owned by user A changes
- **THEN** user A's socket receives the event
- **AND** user B's socket receives nothing

#### Scenario: Every open client of one user is updated

- **WHEN** a user holds sockets from two browsers and a phone
- **AND** one of them changes a task
- **THEN** all three sockets receive the event

### Requirement: Broadcast covers every write path

Task-change events SHALL be emitted from model-level signals, so that a change made through the REST
API, the MCP server, Celery recurring-task generation, or the Django admin all produce the same
event.

#### Scenario: MCP-driven change reaches the browser

- **WHEN** an LLM client updates a task through the MCP server
- **THEN** the user's open browser receives a `task.updated` event

#### Scenario: Recurring-task generation reaches the browser

- **WHEN** the Celery beat job materializes a task from a recurring template
- **THEN** the owner's open clients receive a `task.created` event

### Requirement: Event payloads

An event SHALL carry a `type` of `task.created`, `task.updated`, or `task.deleted`, and the task's
`id`. Created and updated events SHALL additionally carry the full task, serialized in the same shape
the task list endpoint returns, including tags inherited from the task's project.

#### Scenario: Payload is committed state, including inherited tags

- **WHEN** a task is saved with a project whose tags are inherited onto it
- **THEN** the broadcast payload includes those inherited tags

#### Scenario: Rolled-back changes are not broadcast

- **WHEN** a task is saved inside a transaction that then rolls back
- **THEN** no event is sent

#### Scenario: Delete carries only the id

- **WHEN** a task is deleted
- **THEN** a `task.deleted` event carrying that task's `id` is sent to its owner's sockets

### Requirement: Broadcast failure never fails the write

The channel layer SHALL be treated as optional infrastructure. If it is unreachable, the failure
SHALL be logged and swallowed.

#### Scenario: Redis is down

- **WHEN** the Redis channel layer is unreachable
- **AND** a user updates a task through the REST API
- **THEN** the update succeeds and returns normally
- **AND** the broadcast failure is logged
