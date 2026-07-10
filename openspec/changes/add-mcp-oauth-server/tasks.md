## 1. Dependencies & configuration
- [x] 1.1 Add `mcp`, `django-oauth-toolkit`, and `uvicorn` to `pyproject.toml`; run `uv lock`
- [x] 1.2 Add `oauth2_provider` to `INSTALLED_APPS` and its middleware/backends as required
- [x] 1.3 Configure `OAUTH2_PROVIDER` (PKCE required, `read`/`write` scopes, token lifetimes) and
      set `ASGI_APPLICATION` and a sensible `LOGIN_URL`
- [x] 1.4 Add MCP/OAuth config keys to `.env.example` (public base URL, token lifetimes)
- [x] 1.5 Run `migrate` to create the `oauth2_provider` tables

## 2. OAuth authorization server
- [x] 2.1 Mount OAuth endpoints (authorize, token, introspect, revoke) via `oauth2_provider.urls`
- [x] 2.2 Serve RFC 8414 authorization-server metadata at `/.well-known/oauth-authorization-server`
      (thin view — DOT 3.3 only ships OIDC discovery)
- [x] 2.3 Provide RFC 7591 Dynamic Client Registration (`/o/register/`) advertised in the AS metadata
- [x] 2.4 Verify the authorize + PKCE consent flow renders and issues a code/token for a logged-in user

## 3. MCP server & auth bridge
- [x] 3.1 Create `mcp_server/` package with a FastMCP (official SDK) Streamable HTTP app
- [x] 3.2 Implement an OAuth `TokenVerifier` that introspects DOT access tokens in-process, checks
      expiry + scope, and resolves the Django user
- [x] 3.3 Serve RFC 9728 Protected Resource Metadata at `/.well-known/oauth-protected-resource`
      (the `/mcp` variant); return `401` + `WWW-Authenticate` for unauthenticated `/mcp`
- [x] 3.4 Compose `organizer/asgi.py` to route `/mcp` + well-known to the MCP app, else Django;
      run the MCP session-manager lifespan

## 4. MCP tools (full CRUD, reusing serializers/filters)
- [x] 4.1 Task tools: `list_tasks` (filters + pagination), `get_task`, `create_task`,
      `update_task`, `delete_task` — owner-scoped like `TaskItemViewSet`
- [x] 4.2 Project tools: `list_projects`, `get_project`, `create_project`, `update_project`,
      `delete_project`
- [x] 4.3 Tag tools: `list_tags`, `get_tag`, `create_tag`, `update_tag`, `delete_tag`
- [x] 4.4 Comment tools: `list_task_comments`, `add_task_comment`, `delete_task_comment`
- [x] 4.5 Offload blocking ORM calls (cycling the DB connection) so tool handlers don't block the
      event loop; `write` tools assert the `write` scope

## 5. Tests
- [x] 5.1 Token verifier: valid token resolves the right user; expired/invalid/wrong-scope rejected
- [x] 5.2 Discovery: protected-resource metadata JSON is correct; unauthenticated `/mcp` → 401 with
      `WWW-Authenticate`
- [x] 5.3 Dynamic Client Registration returns a usable `client_id`
- [x] 5.4 Tool behavior: CRUD round-trips for each entity; tasks are owner-scoped; comments record
      the authenticated user
- [x] 5.5 (Live) drove `/mcp` through the real MCP client over uvicorn for `tools/list` + tool calls
      (in-process ASGI transport can't service the concurrent SSE stream, so this is a manual check)

## 6. Docs & housekeeping
- [x] 6.1 Regenerate `requirements.txt` with `uv export`
- [x] 6.2 Update `CLAUDE.md` (architecture, authentication, commands) with the uvicorn run command
      and client connection/setup steps
- [x] 6.3 `uv run ruff check .` clean
- [x] 6.4 `openspec validate add-mcp-oauth-server --strict` passes
