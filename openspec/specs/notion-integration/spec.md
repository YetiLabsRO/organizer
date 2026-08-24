# notion-integration Specification

## Purpose
TBD - created by archiving change add-notion-task-sync. Update Purpose after archive.
## Requirements
### Requirement: Notion account linking
The system SHALL let an authenticated user link their Notion workspace through Notion's OAuth 2.0
authorization-code flow, acting as a confidential client that authenticates to the token endpoint with
HTTP Basic credentials. The flow SHALL be initiated by an authenticated API call that returns an
authorize URL, and completed by a public callback that identifies the user from an unguessable,
single-use, short-lived `state` value. Tokens SHALL be stored encrypted at rest, SHALL never be returned
to clients, and SHALL never be logged.

#### Scenario: Connect returns an authorize URL bound to the user
- **WHEN** an authenticated user requests to connect Notion
- **THEN** the system stores a pending flow bound to that user and returns a Notion authorize URL
  carrying `owner=user`, the registered redirect URI, and that flow's `state`

#### Scenario: Callback links the workspace to the right user
- **WHEN** Notion redirects to the callback with a valid `code` and a known unconsumed `state`
- **THEN** the system exchanges the code using HTTP Basic client authentication, stores the encrypted
  access and refresh tokens, the `bot_id` and the workspace identity against the user bound to that
  `state`, and redirects the browser back into the web app

#### Scenario: Unknown, expired or reused state is rejected
- **WHEN** the callback receives a `state` that is unknown, older than its time-to-live, or already
  consumed
- **THEN** the system rejects the request and stores no credentials

#### Scenario: Disconnecting destroys stored credentials
- **WHEN** a connected user disconnects Notion
- **THEN** the system deletes the stored tokens and all link records for that user

### Requirement: Reactive token refresh with rotation
Because Notion's token response carries no expiry, the system SHALL NOT precompute token expiry. It
SHALL refresh reactively when a request is rejected as unauthorized, retrying the request once, and it
SHALL persist the rotated refresh token returned by each refresh. A refresh rejected as an invalid grant
SHALL mark the connection as needing re-authorization instead of failing the sync run.

#### Scenario: Unauthorized response triggers refresh and retry
- **WHEN** a Notion API call is rejected as unauthorized and a refresh token is stored
- **THEN** the system refreshes the access token, persists the newly returned refresh token, and retries
  the original call once

#### Scenario: Invalid grant marks the connection for re-authorization
- **WHEN** a token refresh is rejected as an invalid grant
- **THEN** the connection is marked as needing re-authorization and the sync run ends without error

### Requirement: Self-provisioned task database
The system SHALL create its own Notion database, under a parent page the user selects from the pages they
shared with the integration, using a schema the system defines. The database SHALL start empty; the system
SHALL NOT adopt a pre-existing database. The system SHALL record both the database id and its data source
id, and SHALL address rows through the data source. All tasks SHALL live in a single data source so that a
task changing project is a property update rather than a page re-parenting, which Notion does not permit.

#### Scenario: User selects a parent page and the database is created
- **WHEN** a connected user chooses one of their shared Notion pages as the parent
- **THEN** the system creates a database under that page with the defined property schema and stores the
  resulting database id and data source id

#### Scenario: Schema covers every task field
- **WHEN** the database is created
- **THEN** its schema contains properties for title, description, status, completion, completion date,
  priority, start date, deadline, estimated time, the for-today flag, tags, project, and parent task,
  plus a read-only last-edited-by property

#### Scenario: Provisioning is required before syncing
- **WHEN** a connection has no provisioned database
- **THEN** no sync runs for that connection and the connection reports that it is not yet provisioned

### Requirement: Resumable bootstrap upload
Because the Notion database starts empty, the system SHALL upload every task owned by the connected user
on first sync, as a background job that records its progress so that an interrupted run resumes rather
than duplicating pages. Incremental syncing SHALL NOT begin until the bootstrap has completed. Select and
multi-select option sets SHALL be seeded onto the data source before the upload.

#### Scenario: Existing tasks populate the empty database
- **WHEN** the bootstrap runs for a newly provisioned connection
- **THEN** every task owned by that user is created as a page in the data source and linked

#### Scenario: Interrupted bootstrap resumes without duplicates
- **WHEN** a bootstrap run is interrupted and later retried
- **THEN** it continues from its recorded progress and does not create a second page for an
  already-uploaded task

#### Scenario: Incremental sync waits for the bootstrap
- **WHEN** a connection's bootstrap has not completed
- **THEN** incremental pull and push do not run for that connection

### Requirement: Two-way task synchronization
The system SHALL synchronize tasks in both directions between Organizer and the provisioned Notion data
source. Pulling SHALL query incrementally on last-edited time with an overlap window that accounts for
Notion rounding that timestamp down to the minute, and applying a pulled page SHALL be idempotent.
Pushing SHALL create pages for unlinked local tasks, update pages for changed linked tasks, and trash
pages for tasks deleted locally. Pull SHALL run before push within a run.

#### Scenario: A task created in Organizer appears in Notion
- **WHEN** a sync runs and the user owns a task that has no linked Notion page
- **THEN** a page is created in the data source with that task's field values and the two are linked

#### Scenario: A page created in Notion appears in Organizer
- **WHEN** a sync pulls a page in the data source that is not linked to a local task
- **THEN** a task is created owned by the connected user with the page's field values, and the two are
  linked

#### Scenario: An edit on either side propagates to the other
- **WHEN** a linked task is edited locally, or its linked page is edited in Notion, and a sync runs
- **THEN** the change is applied to the other side

#### Scenario: A locally deleted task trashes its page
- **WHEN** a mirrored task is deleted in Organizer and a sync runs
- **THEN** its Notion page is moved to the trash and the link is removed

#### Scenario: Re-applying an already-synced page changes nothing
- **WHEN** a pulled page falls inside the overlap window but has already been applied
- **THEN** applying it again produces no change and no further writes

### Requirement: Echo suppression and conflict resolution
The system SHALL NOT treat its own writes as user edits. A pulled page whose last editor is the
connection's own integration bot SHALL be skipped. The system SHALL additionally maintain, per link, a
watermark for each side, and SHALL re-stamp both watermarks after every write on either side so that a
sync-authored change is never read back as a user edit. When both sides changed since the last sync, the
more recent change SHALL win; when the two timestamps fall within the same minute and cannot be ordered,
Organizer SHALL win. Conflict outcomes SHALL be logged.

#### Scenario: The integration's own edit is not pulled back
- **WHEN** a pulled page reports the connection's own bot as its last editor
- **THEN** the page is skipped and no local change is made

#### Scenario: Applying an inbound change does not push it back
- **WHEN** a sync applies an inbound change to a task and a subsequent sync runs with no user activity
- **THEN** the subsequent sync makes no writes to either side

#### Scenario: The more recent change wins
- **WHEN** both a task and its page changed since the last sync, in different minutes
- **THEN** the side with the more recent change is applied to the other and the outcome is logged

#### Scenario: A same-minute conflict resolves to Organizer
- **WHEN** both sides changed and their timestamps fall within the same minute
- **THEN** the Organizer values are pushed to Notion and the outcome is logged

### Requirement: Full reconciliation and deletion detection
The system SHALL periodically walk the entire data source without an incremental filter, to repair drift
the minute-granularity change feed cannot see and to detect pages deleted in Notion. Because the query
endpoint returns only non-archived rows and cannot filter on trashed state, a link whose page is absent
from the sweep SHALL be confirmed by retrieving that page directly before the mirrored local task is
deleted.

#### Scenario: A page trashed in Notion deletes the mirrored task
- **WHEN** a full reconciliation finds a link whose page no longer appears in the data source, and
  retrieving that page confirms it is trashed
- **THEN** the mirrored local task is deleted and the link is removed

#### Scenario: A transiently missing page is not deleted
- **WHEN** a link's page is absent from the sweep but retrieving it shows the page is not trashed
- **THEN** the local task is kept

### Requirement: Global projects and tags are matched, never created
Projects and tags are shared across all users of this deployment. The system SHALL resolve an inbound
project or tag value against existing records and SHALL NOT create new projects or tags from Notion
values. Unresolved values SHALL be ignored and logged.

#### Scenario: A known project moves the task
- **WHEN** a pulled page names a project that matches an existing project
- **THEN** the mirrored task is assigned to that project

#### Scenario: An unknown project is ignored
- **WHEN** a pulled page names a project or tag with no matching existing record
- **THEN** the value is ignored, the task's current project and tags are left unchanged, and the event is
  logged

### Requirement: Owner scoping
Every synchronization operation SHALL be scoped to the connected user. The push phase SHALL only consider
tasks owned by the connection's user, and every synchronization endpoint SHALL act only on the requesting
user's own connection.

#### Scenario: Another user's task is never pushed
- **WHEN** a sync runs and another user owns a task in a project that the connected user also uses
- **THEN** that task is not created in the connected user's Notion workspace

#### Scenario: Endpoints act only on the caller's connection
- **WHEN** an authenticated user calls a Notion integration endpoint
- **THEN** it reads or modifies only that user's own connection

### Requirement: Schema drift detection
The system SHALL address Notion properties by the property identifiers recorded at provisioning time, so
that renaming a property in Notion does not break the sync. Before syncing, the system SHALL verify those
identifiers still exist; if a required property is missing, the connection SHALL be paused in a
schema-drift state rather than silently dropping the field.

#### Scenario: A renamed property still syncs
- **WHEN** a user renames a property in Notion and a sync runs
- **THEN** the sync continues to map that property correctly

#### Scenario: A deleted property pauses the sync
- **WHEN** a required property no longer exists in the data source
- **THEN** the connection is marked as having schema drift, no records are written, and the condition is
  reported to the user

### Requirement: Rate-limited API access
The system SHALL pace its Notion API requests to stay within Notion's documented average rate, SHALL
honour the retry delay Notion returns when rate limited, and SHALL back off on server errors. A failing
connection SHALL NOT abort synchronization for other connections.

#### Scenario: Requests are paced
- **WHEN** the system issues a burst of Notion API calls
- **THEN** they are paced to the configured average request rate

#### Scenario: Rate limiting is honoured
- **WHEN** Notion rejects a request as rate limited and supplies a retry delay
- **THEN** the system waits at least that long before retrying

#### Scenario: One failing connection does not stop the batch
- **WHEN** a scheduled run syncs several connections and one raises an error
- **THEN** that connection's error is recorded and the remaining connections are still synced

### Requirement: Synchronization triggers
The system SHALL synchronize on a recurring schedule, SHALL provide a management command for manual and
full runs, and SHALL expose an authenticated endpoint that enqueues a sync for the requesting user.

#### Scenario: Scheduled synchronization
- **WHEN** the configured interval elapses
- **THEN** the system synchronizes every active, provisioned connection

#### Scenario: On-demand synchronization is enqueued
- **WHEN** an authenticated user triggers a sync
- **THEN** a sync is enqueued for that user's connection and the request returns without waiting for it
  to finish

#### Scenario: Command-line synchronization
- **WHEN** an operator runs the sync management command, optionally for one user or as a full run
- **THEN** the selected connections are synchronized in that mode

