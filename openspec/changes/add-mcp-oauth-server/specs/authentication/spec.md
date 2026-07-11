## ADDED Requirements

### Requirement: OAuth 2.1 authorization server
The system SHALL act as an OAuth 2.1 authorization server issuing access tokens via the
authorization-code grant with PKCE. The authorize endpoint SHALL require an authenticated Django
user and SHALL present a consent step before issuing an authorization code. Issued access tokens
SHALL carry scopes and be revocable.

#### Scenario: Authorization code with PKCE
- **WHEN** a registered client sends the user through the authorize endpoint with a PKCE challenge
  and the user logs in and grants access
- **THEN** an authorization code is issued and can be exchanged at the token endpoint (with the PKCE
  verifier) for an access token

#### Scenario: Missing PKCE is rejected
- **WHEN** a client initiates the authorization-code flow without a PKCE challenge
- **THEN** the request is rejected

### Requirement: OAuth scopes
The system SHALL define `read` and `write` scopes for OAuth access tokens. Read operations SHALL
require `read`; create, update, and delete operations SHALL require `write`.

#### Scenario: Write requires the write scope
- **WHEN** a client presents a token that has `read` but not `write` and attempts a mutating operation
- **THEN** the operation is rejected as insufficiently scoped

### Requirement: Authorization server metadata
The system SHALL serve OAuth 2.0 Authorization Server Metadata (RFC 8414) at
`/.well-known/oauth-authorization-server`, advertising the authorize, token, and dynamic client
registration endpoints and the supported scopes.

#### Scenario: Client discovers endpoints
- **WHEN** a client GETs `/.well-known/oauth-authorization-server`
- **THEN** the response advertises the authorization, token, and registration endpoints and the
  supported scopes

### Requirement: Dynamic client registration
The system SHALL allow OAuth clients to register dynamically (RFC 7591) by POSTing their metadata
(including redirect URIs) and receiving a `client_id`, so MCP clients can self-register without
manual configuration.

#### Scenario: Client self-registers
- **WHEN** a client POSTs valid registration metadata to the registration endpoint
- **THEN** the server creates a public authorization-code + PKCE client and returns a `client_id`
