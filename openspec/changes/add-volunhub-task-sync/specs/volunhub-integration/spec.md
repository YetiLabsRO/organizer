## ADDED Requirements

### Requirement: Confined client registration
The system SHALL register itself with VolunHub as an OAuth 2.1 public client using RFC 7591 Dynamic
Client Registration. It SHALL register once per VolunHub base URL and redirect URI, never per user or
per connect, using endpoints discovered from VolunHub's authorization-server metadata. The
registration SHALL declare `token_endpoint_auth_method: "none"`, the `authorization_code` and
`refresh_token` grant types, the `code` response type, and exactly the scope
`mcp:tasks:read mcp:tasks:write`. The system SHALL persist the returned `client_id` only if the
returned scope set is exactly those two scopes; otherwise it SHALL discard the registration and fail
the connect attempt. An operator-supplied client id SHALL take precedence over registration.

#### Scenario: First connect registers and persists the client
- **WHEN** a user connects and no client is stored for the configured base URL and redirect URI
- **THEN** the system registers a public client requesting exactly `mcp:tasks:read mcp:tasks:write`
  and persists the returned `client_id` for reuse by every user

#### Scenario: Stored client is reused
- **WHEN** another user connects after a client has been registered
- **THEN** the stored `client_id` is used and no new registration is made

#### Scenario: Broader registration is refused
- **WHEN** the registration response's scope is missing or differs from exactly
  `mcp:tasks:read mcp:tasks:write`
- **THEN** the system does not persist the client and the connect attempt fails with an error

### Requirement: VolunHub account linking with PKCE
The system SHALL let an authenticated user link their VolunHub account with the authorization-code
grant and PKCE (S256).
- **Starting a link** SHALL be an authenticated API call. It SHALL store a pending flow that binds an
  unguessable, single-use, short-lived `state` to the user and the PKCE `code_verifier`, and return
  the VolunHub authorize URL.
- **Completing a link** SHALL happen at a public browser callback. The callback SHALL resolve the user
  from the `state`, exchange the code using the `client_id` and `code_verifier` without any client
  secret, and store the tokens encrypted at rest against that user.
- **Granted scope**: a grant without `mcp:tasks:read` SHALL be rejected, and a grant without
  `mcp:tasks:write` SHALL produce a read-only connection.
- **Tokens** SHALL never be returned to clients or logged.

#### Scenario: Connect returns a PKCE authorize URL
- **WHEN** an authenticated user requests to connect VolunHub
- **THEN** the system stores a pending flow bound to that user and returns an authorize URL carrying the
  `client_id`, the exact registered redirect URI, scope `mcp:tasks:read mcp:tasks:write`, the flow's
  `state`, and an S256 `code_challenge`

#### Scenario: Callback links the account to the right user
- **WHEN** VolunHub redirects to the callback with a valid `code` and a known unconsumed `state`
- **THEN** the system exchanges the code with the `code_verifier` and no client secret, stores the
  encrypted tokens, expiry and granted scope against the user bound to that `state`, and redirects the
  browser back to the integrations screen

#### Scenario: Unknown, expired or reused state is rejected
- **WHEN** the callback receives a `state` that is unknown, older than its time-to-live, or already
  consumed
- **THEN** no token exchange happens and no credentials are stored

#### Scenario: Write scope declined yields a read-only connection
- **WHEN** the user unticks the write permission on VolunHub's consent screen
- **THEN** the connection is stored as read-only and the system pushes no changes to VolunHub for it

### Requirement: Serialized token refresh with rotation
The system SHALL refresh an access token before it expires and when a request is rejected as
unauthorized, retrying the request once. It SHALL persist the rotated refresh token returned by every
refresh. Refreshes for one connection SHALL be serialized: a worker that finds the token already
refreshed by another SHALL use it instead of refreshing again. A refresh rejected as an invalid grant
SHALL mark the connection as needing re-authorization without failing the sync run.

#### Scenario: Near-expiry token is refreshed proactively
- **WHEN** a sync starts and the stored access token expires within a minute
- **THEN** the system refreshes it first and persists both the new access token and the rotated refresh
  token

#### Scenario: Concurrent refreshes do not invalidate the connection
- **WHEN** two workers need a refresh for the same connection at the same time
- **THEN** only one refresh request is sent to VolunHub and both workers use the resulting token

#### Scenario: Invalid grant marks the connection for re-authorization
- **WHEN** a refresh is rejected as an invalid grant
- **THEN** the connection is marked as needing re-authorization and the sync run ends without error

### Requirement: Disconnect
The system SHALL let a connected user disconnect VolunHub. Disconnecting SHALL revoke the tokens
best-effort at VolunHub's revocation endpoint, delete the stored credentials, and mark every active
task link as removed with the reason "disconnected", keeping the local tasks.

#### Scenario: Disconnect keeps tasks and stops syncing
- **WHEN** a connected user disconnects
- **THEN** the tokens are revoked best-effort and deleted, the user's VolunHub-linked tasks remain
  as local tasks marked removed with reason "disconnected", and no further VolunHub calls are made
  for that user

#### Scenario: Reconnect re-attaches existing tasks
- **WHEN** the user reconnects and a task they previously had linked appears in the listing again
- **THEN** the existing local task is re-attached and synced, and no duplicate task is created

### Requirement: Confined API access
The system SHALL call only VolunHub's `/api/v1/projects/tasks` and `/api/v1/projects/projects` path
prefixes, and SHALL refuse to send a request to any other path. It SHALL back off on rate-limit and
server errors, honouring `Retry-After` when present.

#### Scenario: Off-list path is never requested
- **WHEN** code attempts a VolunHub request outside the two allowed path prefixes
- **THEN** the client raises an error and no request is sent

### Requirement: Import of assigned tasks
On every sync the system SHALL read the user's complete assigned-task listing
(`/api/v1/projects/tasks/?mine=true`, ordered by id, following pagination to the end). It SHALL create
a local task, owned by the user, for each VolunHub task not yet linked, and link it by external id. If
any page of the listing fails, the run SHALL stop without applying merges or removals. Completion and
status SHALL be derived from the task's workflow state (`state_name`), never from the listing's
`completed` column.

#### Scenario: New assigned task is imported
- **WHEN** a sync finds a VolunHub task with no link for the user
- **THEN** a local task owned by the user is created from the mapped VolunHub values and linked to the
  external id

#### Scenario: Pagination is followed to the end
- **WHEN** the user's assigned tasks span several pages
- **THEN** every page is read before any task is merged or removed

#### Scenario: Partial listing aborts the run
- **WHEN** fetching any page of the listing fails
- **THEN** no local task is changed or marked removed in that run

#### Scenario: Finished state marks the task completed
- **WHEN** a VolunHub task's state is "Finalizat" while its `completed` column is false
- **THEN** the local task is completed

### Requirement: Field mapping
The system SHALL map these fields both ways:
- title ↔ title;
- description ↔ description;
- start date ↔ `start_date`;
- the local end date (deadline) ↔ VolunHub `deadline`;
- estimated time ↔ `estimated_time` (minutes);
- priority low/normal/high ↔ 1/2/3;
- status and completion ↔ workflow state.

VolunHub `draft` and `planned` SHALL map to `idea`, `in_progress` to `inprogress`, `blocked` to
`blocked`, and `finished` to completed. A local `givenup` status SHALL NOT be pushed. A task with no
workflow state SHALL NOT have its status synced. Comparisons SHALL normalize datetimes to UTC and
blank descriptions to empty.

#### Scenario: Priority round-trips
- **WHEN** a VolunHub task has priority 3
- **THEN** the local task has high priority, and setting it back to normal locally pushes priority 2

#### Scenario: Timezone-only difference is not a change
- **WHEN** VolunHub returns a deadline in `+03:00` that denotes the same instant as the snapshot
- **THEN** the deadline is not treated as changed

#### Scenario: Given-up is not pushed
- **WHEN** a linked task's local status is set to `givenup`
- **THEN** no status change is sent to VolunHub for that task and the local status is kept

### Requirement: Two-way three-way merge
For every linked active task, the system SHALL keep a snapshot of the last values both sides agreed on.
For each synced field it SHALL compare the current VolunHub value and the current local value against
that snapshot:
- changed only in VolunHub → applied locally;
- changed only locally → pushed to VolunHub;
- changed on both sides to different values → the local value is pushed and the conflict is logged.

A field the system cannot currently push SHALL take the VolunHub value when VolunHub changes it. After
every successful write the snapshot SHALL be updated, so the system's own writes are never read back as
changes. A failed push SHALL leave the snapshot unchanged for that field so it is retried, and SHALL be
recorded on the link.

#### Scenario: Remote edit is applied locally
- **WHEN** a task's title changed in VolunHub since the last sync and is unchanged locally
- **THEN** the local title is updated from VolunHub

#### Scenario: Local edit is pushed
- **WHEN** a linked task's description was edited locally and is unchanged in VolunHub
- **THEN** the system sends a partial update with only the description to VolunHub

#### Scenario: Conflicting edits keep the local value
- **WHEN** the same field changed to different values on both sides since the last sync
- **THEN** the local value is pushed to VolunHub and a conflict is logged

#### Scenario: Own writes are not echoed
- **WHEN** the run after a successful push reads the task back from VolunHub
- **THEN** no field is applied locally or pushed again

### Requirement: Status write-back through the workflow
The system SHALL push local status and completion changes with VolunHub's task status endpoint, using
the field mapping. When the target state is not directly reachable from the current state, the system
SHALL first transition through `planned`. An unreachable transition (`409`) or a rejected request
(`400`) SHALL be recorded on the task's link without aborting the run, and SHALL be retried on later
runs.

#### Scenario: Local completion is pushed as finished
- **WHEN** a linked task is completed locally
- **THEN** the system requests state `finished` for it in VolunHub

#### Scenario: Reopening to in-progress takes two steps
- **WHEN** a task finished in VolunHub is set locally to not completed with status `inprogress`
- **THEN** the system requests `planned` and then `in_progress`

#### Scenario: Unreachable transition does not abort the run
- **WHEN** VolunHub answers `409` to a status change
- **THEN** the error is recorded on that task's link and the remaining tasks are still synced

### Requirement: Content write-back degrades to status-only
The system SHALL push local content changes (title, description, start date, deadline, estimated
time, priority) with a partial update containing only the changed fields. It SHALL never create or
delete tasks in VolunHub. If VolunHub rejects a content update as forbidden (`403`), the system SHALL
disable content push for that connection, keep pushing status, treat content fields as import-only,
and surface the condition, until the user reconnects or explicitly re-enables content push.

#### Scenario: Forbidden content update disables content push
- **WHEN** VolunHub answers `403` to a partial update of a task in the user's own listing
- **THEN** content push is disabled for the connection, status changes are still pushed, and the
  integration status reports it

#### Scenario: Local delete never deletes upstream
- **WHEN** the user deletes a VolunHub-linked task in Organizer
- **THEN** no delete request is sent to VolunHub and the task is not imported again while it remains
  assigned

### Requirement: Externally removed tasks are kept and marked
When a linked active task is absent from a complete listing, the system SHALL look the task up by id:
- not found → mark the link removed with reason "deleted";
- found → mark it removed with reason "unassigned";
- any other outcome → leave the link unchanged.

Marking a task removed SHALL NOT alter or delete the local task. A removed task that reappears in the
listing SHALL be re-attached to the same local task.

#### Scenario: Unassigned task is kept and marked
- **WHEN** a linked task disappears from the user's listing but is still retrievable by id
- **THEN** the local task is kept unchanged and marked removed from VolunHub with reason "unassigned"

#### Scenario: Deleted task is kept and marked
- **WHEN** a linked task disappears from the listing and its lookup returns not found
- **THEN** the local task is kept unchanged and marked removed from VolunHub with reason "deleted"

#### Scenario: Lookup failure changes nothing
- **WHEN** the lookup of a missing task fails with a server or network error
- **THEN** the link stays active and the check is repeated next run

#### Scenario: Reassigned task is re-attached
- **WHEN** a task marked removed appears in the listing again
- **THEN** its link becomes active again and the same local task resumes syncing

### Requirement: Project auto-creation and merge
The system SHALL resolve each VolunHub task's project from the project fields inline on the task. The
first time a VolunHub project is seen, the system SHALL create a local project with its name and link
it, and SHALL reuse that link for every later task and user. The system SHALL let a user merge a linked
project into an existing local project:
- the link is re-pointed to the target;
- the tasks of the previous auto-created project are moved to the target;
- the auto-created project is deleted once it has no tasks.

An auto-created project SHALL follow VolunHub renames until it is merged. Project membership SHALL be
import-only: a project change made in VolunHub is applied locally, and a local project change is kept
and never pushed. Only users with a task linked to that VolunHub project SHALL be able to see or merge
its link.

#### Scenario: Unknown project is auto-created
- **WHEN** an imported task belongs to a VolunHub project with no link
- **THEN** a local project with that name is created, linked, and assigned to the task

#### Scenario: Merge into an existing project
- **WHEN** the user merges an auto-created VolunHub project into an existing local project
- **THEN** the link points to the existing project, the moved tasks belong to it, the empty
  auto-created project is deleted, and later imports use the existing project

#### Scenario: Merged project is not renamed
- **WHEN** a merged VolunHub project is renamed in VolunHub
- **THEN** the local project keeps its own name

#### Scenario: Local project move is kept
- **WHEN** the user moves a linked task to another local project and VolunHub's project for it is
  unchanged
- **THEN** the task keeps the local project and nothing is pushed

### Requirement: Synchronization triggers and owner scoping
The system SHALL sync all active connections on a periodic Celery beat schedule, isolating failures per
connection and skipping connections that need re-authorization. It SHALL provide an authenticated
endpoint that queues a sync of only the requesting user's connection, and a management command that
syncs all connections or a single user's. At most one sync SHALL run per connection at a time. Every
sync operation and endpoint SHALL act only on the requesting or connected user's own data.

#### Scenario: Periodic sync isolates failures
- **WHEN** the scheduled sync runs and one user's VolunHub calls fail
- **THEN** the other users' connections are still synced

#### Scenario: Overlapping runs are prevented
- **WHEN** a "sync now" is requested while a scheduled sync of the same connection is running
- **THEN** the second run is skipped rather than running concurrently

#### Scenario: Sync now acts only on the caller
- **WHEN** an authenticated user calls the sync-now endpoint
- **THEN** only that user's connection is queued for sync
