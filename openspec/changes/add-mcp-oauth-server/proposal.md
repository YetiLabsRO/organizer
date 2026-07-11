# Change: OAuth-protected MCP server for tasks, projects, and tags

## Why
The organizer's data (tasks, projects, tags, comments) is only reachable through the DRF HTTP API
consumed by the Angular SPA. There is no way for an LLM assistant (Claude and other MCP clients) to
read or manage that data conversationally. We want a remote **Model Context Protocol** server,
secured with **OAuth 2.1**, that exposes the existing entities as MCP tools so a user can interact
with their organizer from an LLM after logging in and granting access.

## What Changes
- Add an **OAuth 2.1 Authorization Server** to the Django app via `django-oauth-toolkit`:
  authorization-code + **PKCE**, opaque access tokens, scopes (`read`, `write`), token
  introspection, RFC 8414 authorization-server metadata, and RFC 7591 **Dynamic Client
  Registration** so MCP clients can self-register.
- Add an in-tree **remote MCP server** (Streamable HTTP) mounted at `/mcp`, built on the official
  MCP Python SDK. It authenticates every request with an OAuth bearer token (validated in-process
  against the toolkit's tokens) and resolves it to a Django user.
- Serve RFC 9728 **Protected Resource Metadata** at `/.well-known/oauth-protected-resource` so
  clients can discover the authorization server. Unauthenticated `/mcp` requests return `401` with a
  `WWW-Authenticate` header pointing at that metadata.
- Expose **full CRUD MCP tools** for tasks, projects, tags, and task comments, reusing the existing
  DRF serializers and task filters. Tasks stay scoped to the authenticated owner, mirroring the API.
- Run Django under **ASGI** (add `uvicorn`) since Streamable HTTP + the MCP session manager require
  an async server. WSGI deploys keep working for the plain REST API.

## Impact
- Affected specs: **mcp-server** (new capability), **authentication** (adds the OAuth 2.1 server).
- Affected code:
  - `pyproject.toml` / `uv.lock` — add `mcp`, `django-oauth-toolkit`, `uvicorn`; regenerate
    `requirements.txt`.
  - `organizer/settings.py` — `oauth2_provider` app, `OAUTH2_PROVIDER` config, `ASGI_APPLICATION`,
    scopes, `LOGIN_URL`.
  - `organizer/urls.py` — mount OAuth endpoints + authorization-server metadata.
  - `organizer/asgi.py` — top-level ASGI app routing `/mcp` and the well-known metadata to the MCP
    app and everything else to Django.
  - New `mcp_server/` package — MCP app, tool definitions, OAuth token verifier, DCR view,
    protected-resource metadata.
  - `.env.example`, `CLAUDE.md` — new config keys and run instructions.
  - Tests under `mcp_server/tests/` (and `tasks/` where serializers are exercised headlessly).
