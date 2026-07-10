## ADDED Requirements

### Requirement: Remote MCP endpoint over Streamable HTTP
The system SHALL expose a Model Context Protocol server over the Streamable HTTP transport at `/mcp`,
served by the application's ASGI entrypoint. The server SHALL advertise its tools via the MCP
`tools/list` operation.

#### Scenario: List available tools
- **WHEN** an authenticated MCP client calls `tools/list` against `/mcp`
- **THEN** the server returns the task, project, tag, and comment tools

#### Scenario: Streamable HTTP transport is served under ASGI
- **WHEN** the application is run under its ASGI entrypoint
- **THEN** `/mcp` accepts MCP Streamable HTTP requests while all non-`/mcp` routes continue to serve
  the existing Django REST API and admin

### Requirement: OAuth-protected access
The system SHALL require a valid OAuth 2.1 bearer access token on every MCP request, resolve it to a
Django user, and reject missing, invalid, expired, or insufficiently-scoped tokens.

#### Scenario: Authenticated request succeeds
- **WHEN** a client calls `/mcp` with a valid `Authorization: Bearer <token>` header
- **THEN** the request is authenticated as the token's user and processed

#### Scenario: Unauthenticated request is challenged
- **WHEN** a client calls `/mcp` without a valid bearer token
- **THEN** the server responds `401` with a `WWW-Authenticate` header referencing the protected
  resource metadata

### Requirement: Protected resource discovery
The system SHALL serve OAuth 2.0 Protected Resource Metadata (RFC 9728) at
`/.well-known/oauth-protected-resource` identifying this resource and its authorization server(s),
so MCP clients can discover where to obtain a token.

#### Scenario: Client discovers the authorization server
- **WHEN** a client GETs `/.well-known/oauth-protected-resource`
- **THEN** the response lists the MCP resource and the authorization server issuer and supported scopes

### Requirement: Task tools
The system SHALL provide MCP tools to list (with the same filters and pagination as the task API),
retrieve, create, update, and delete tasks. Task tools SHALL operate only on tasks owned by the
authenticated user.

#### Scenario: Create a task via MCP
- **WHEN** an authenticated client calls the create-task tool with a title
- **THEN** a task owned by the authenticated user is created and returned

#### Scenario: List is scoped to the owner
- **WHEN** an authenticated client lists tasks
- **THEN** only tasks owned by the authenticated user are returned

#### Scenario: Filter and search tasks
- **WHEN** an authenticated client lists tasks with a search term, status, priority, tag, or
  `for_today` filter
- **THEN** only matching owned tasks are returned

#### Scenario: Delete a task via MCP
- **WHEN** an authenticated client calls the delete-task tool for one of its tasks
- **THEN** the task is deleted

### Requirement: Project tools
The system SHALL provide MCP tools to list, retrieve, create, update, and delete projects.

#### Scenario: Create and list projects via MCP
- **WHEN** an authenticated client creates a project and then lists projects
- **THEN** the created project appears in the list

### Requirement: Tag tools
The system SHALL provide MCP tools to list, retrieve, create, update, and delete tags.

#### Scenario: Create and list tags via MCP
- **WHEN** an authenticated client creates a tag and then lists tags
- **THEN** the created tag appears in the list

### Requirement: Task comment tools
The system SHALL provide MCP tools to list the comments of a task, add a comment to a task, and
delete a comment. Added comments SHALL record the authenticated user as their author.

#### Scenario: Add a comment via MCP
- **WHEN** an authenticated client adds a comment to a task
- **THEN** the comment is stored against that task with the authenticated user as author
