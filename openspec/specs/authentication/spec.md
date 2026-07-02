# authentication Spec

## Purpose
Authenticate API clients (end users via DRF token login) and gate all domain endpoints behind
authentication.

## Requirements

### Requirement: Token login
The system SHALL provide a login endpoint that accepts user credentials and returns an
authentication token. The token response SHALL include the token key, the user's username, and the
user's role.

#### Scenario: Successful login returns an enriched token
- **WHEN** a client POSTs valid credentials to `/rest-auth/login/`
- **THEN** the response contains `{ key, user, role }`

#### Scenario: Invalid credentials are rejected
- **WHEN** a client POSTs invalid credentials to `/rest-auth/login/`
- **THEN** login fails and no token is issued

### Requirement: Token-authenticated requests
The system SHALL accept the issued token via the `Authorization: Token <key>` header for
authenticating API requests.

#### Scenario: Authenticated API request succeeds
- **WHEN** a client sends a valid `Authorization: Token <key>` header to an API endpoint
- **THEN** the request is authenticated and processed

### Requirement: Authentication required by default
The system SHALL require authentication for all API endpoints by default.

#### Scenario: Anonymous access denied
- **WHEN** an unauthenticated client requests any `/api/` endpoint
- **THEN** the request is denied with 401/403
