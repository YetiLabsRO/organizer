## ADDED Requirements

### Requirement: Notion connection management UI
The web frontend SHALL provide an integrations settings surface where an authenticated user can see their
Notion connection status and the linked workspace, connect by navigating to the authorize URL returned by
the backend, disconnect, and trigger an on-demand sync. It SHALL prompt the user to reconnect when the
connection needs re-authorization, and SHALL never display the raw OAuth tokens. Because Notion offers no
token revocation endpoint, disconnecting SHALL also tell the user how to remove the connection from their
Notion settings.

#### Scenario: Connect starts the OAuth flow
- **WHEN** a user clicks "Connect Notion" on the integrations screen
- **THEN** the app requests an authorize URL from the backend and navigates the browser to Notion's
  consent page

#### Scenario: Connected status offers sync and disconnect
- **WHEN** the user has an active Notion connection
- **THEN** the integrations screen shows the linked workspace with "Sync now" and "Disconnect" actions
  and the time of the last sync

#### Scenario: Reconnect prompt when re-authorization is needed
- **WHEN** the connection needs re-authorization
- **THEN** the integrations screen prompts the user to reconnect

#### Scenario: Disconnect explains how to fully revoke access
- **WHEN** the user disconnects Notion
- **THEN** the app tells them to also remove the connection in their Notion workspace settings

### Requirement: Database provisioning UI
The web frontend SHALL let a connected user choose which of their shared Notion pages the task database
is created under, and SHALL show that the database is created empty and then populated from their
existing tasks. It SHALL surface bootstrap progress, and once provisioned SHALL link to the Notion
database.

#### Scenario: User picks a parent page
- **WHEN** a connected user has not yet provisioned a database
- **THEN** the screen lists the Notion pages shared with the integration and lets the user pick one as
  the parent

#### Scenario: Bootstrap progress is visible
- **WHEN** the initial upload of existing tasks is running
- **THEN** the screen reports that it is in progress rather than appearing idle

#### Scenario: Provisioned database is linked
- **WHEN** the database has been created
- **THEN** the screen links to it in Notion

#### Scenario: No shared pages is explained
- **WHEN** the user shared no pages with the integration during consent
- **THEN** the screen explains that they must grant access to a page in Notion before a database can be
  created

### Requirement: Notion sync disclosure and source indication
The web frontend SHALL visually indicate tasks mirrored to Notion and link them to their Notion page. It
SHALL disclose the behaviours that would otherwise surprise the user: that the Notion page body is never
synchronized, that deleting a task on either side removes it from the other, and that projects and tags
typed in Notion are matched against existing ones rather than created.

#### Scenario: Mirrored task shows a source badge
- **WHEN** a task mirrored to Notion is displayed in a list or detail view
- **THEN** it shows a Notion source indicator linking to its Notion page

#### Scenario: Unsynced page body is disclosed
- **WHEN** the user views the Notion integration screen
- **THEN** it states that content written in the body of a Notion task page stays in Notion and is not
  imported

#### Scenario: Destructive behaviour is disclosed
- **WHEN** the user views the Notion integration screen
- **THEN** it states that deleting a task in Organizer trashes its Notion page and that trashing a page
  in Notion deletes the task in Organizer
