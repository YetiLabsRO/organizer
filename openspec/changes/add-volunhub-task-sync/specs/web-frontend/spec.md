## ADDED Requirements

### Requirement: VolunHub connection management UI
The integrations screen (`/settings/integrations`) SHALL include a VolunHub section where an
authenticated user can see the connection status and last sync time, connect (by navigating to the
authorize URL returned by the backend), trigger a sync, and disconnect. It SHALL handle the callback's
`volunhub=connected|error` return, prompt for reconnection when re-authorization is needed, explain a
read-only connection and a disabled content push, and never display OAuth tokens.

#### Scenario: Connect starts the OAuth flow
- **WHEN** the user clicks "Connect VolunHub"
- **THEN** the app requests an authorize URL from the backend and navigates the browser to it

#### Scenario: Connected state offers sync and disconnect
- **WHEN** the user has an active VolunHub connection
- **THEN** the section shows the connected state, the last sync time, and "Sync now" and "Disconnect"
  actions

#### Scenario: Re-authorization prompt
- **WHEN** the connection needs re-authorization
- **THEN** the section prompts the user to reconnect

#### Scenario: Content push disabled is explained
- **WHEN** content push has been disabled because VolunHub refused a content update
- **THEN** the section explains that only status changes are sent to VolunHub and offers to retry

### Requirement: VolunHub project merge UI
The VolunHub section SHALL list the VolunHub projects linked through the user's tasks, each with its
local project, and SHALL let the user merge an auto-created project into an existing local project.

#### Scenario: Merge from the integrations screen
- **WHEN** the user picks an existing local project as the merge target for a VolunHub project
- **THEN** the app calls the merge endpoint and the list shows the VolunHub project mapped to the
  chosen project

### Requirement: VolunHub sync disclosure and source indication
The web frontend SHALL mark tasks linked to VolunHub with a source badge linking to the task in
VolunHub, and SHALL mark tasks removed from VolunHub with a distinct badge stating the reason. The
VolunHub section SHALL disclose these behaviours:
- only tasks personally assigned to the user are imported;
- edits sync both ways, and on a conflicting edit Organizer's value wins;
- edits notify the task's watchers in VolunHub;
- Organizer never creates or deletes VolunHub tasks;
- a local "given up" status, tags, subtasks and "for today" stay local;
- VolunHub-sourced tasks are not mirrored to Notion.

#### Scenario: Linked task shows a VolunHub badge
- **WHEN** a VolunHub-linked task is displayed in a list or detail view
- **THEN** it shows a VolunHub source indicator linking to the task in VolunHub

#### Scenario: Removed task shows the removal reason
- **WHEN** a task whose link is marked removed is displayed
- **THEN** it shows that it was removed from VolunHub, with the reason (unassigned, deleted or
  disconnected)

#### Scenario: Behaviours are disclosed
- **WHEN** the user views the VolunHub section
- **THEN** it states that deleting a task in Organizer does not delete it in VolunHub and that edits
  notify VolunHub watchers
