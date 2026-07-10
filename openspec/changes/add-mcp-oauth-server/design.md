## Context
The backend is a Django 6 + DRF monolith with a single `tasks` app and default `auth.User`. Auth
today is DRF Token (dj-rest-auth) and scoutfile SSO JWT. We are adding a remote, OAuth-protected MCP
server so LLM clients (primary target: Claude) can manage tasks/projects/tags/comments. Decisions
below were confirmed with the maintainer: self-hosted OAuth via django-oauth-toolkit, in-tree
single-service deployment, and full CRUD.

## Goals / Non-Goals
- Goals:
  - Standards-compliant remote MCP server usable by Claude and any other MCP client.
  - OAuth 2.1 (auth code + PKCE) issued by this app; user logs in once, grants access, revocable.
  - Full CRUD over tasks, projects, tags, and task comments, reusing existing serializers/filters.
  - Owner-scoped task access identical to the REST API.
- Non-Goals:
  - Replacing the existing DRF Token / SSO JWT auth (they remain untouched).
  - Multi-tenant authorization beyond the current per-owner task scoping.
  - Streaming/resources/prompts beyond tools (tools only in v1).
  - Rewriting the REST API to async; only the ASGI entrypoint is added.

## Decisions

### Decision: Authorization server = django-oauth-toolkit (DOT)
Self-host the OAuth 2.1 AS in-process. Rationale: no third-party dependency for a personal app, it
reuses `auth.User` and Django's session login for the consent screen, and it gives us authorize +
token + introspection + revocation for free.
- `PKCE_REQUIRED = True`; public clients supported (Claude registers as a public client + PKCE).
- Access tokens are **opaque** (not JWT). The MCP server introspects them **in-process** by loading
  the toolkit `AccessToken` row (no network/JWKS round-trip), checking expiry + scope, and reading
  `token.user`.
- Scopes: `read` (list/get) and `write` (create/update/delete). The token endpoint grants both by
  default; mutating tools additionally assert `write`.
- Alternatives considered: external IdP (rejected — extra infra for a personal app); JWT access
  tokens + JWKS verification (rejected — unnecessary indirection when the AS and RS share a process);
  reusing scoutfile SSO (rejected — not an interactive AS, no DCR/PKCE browser flow).

### Decision: MCP server = official MCP Python SDK, Streamable HTTP, mounted in-tree
Build the server with the reference `mcp` SDK (FastMCP) using the Streamable HTTP transport, and
mount its ASGI app at `/mcp`. Tools call the Django ORM/DRF serializers **directly in-process**
(no HTTP hop back to `/api/`). Rationale: one deploy, one credential path, reuse of serializers and
`TaskFilterSet` as the single source of truth for field shape and validation.
- Auth is enforced by a `TokenVerifier` that wraps the DOT in-process introspection above and
  returns the SDK `AccessToken` (carrying scopes + the Django user id) so tools can resolve the user.
- Alternatives considered: standalone MCP service calling the REST API over HTTP (rejected — second
  service, network re-auth); hand-rolling the Streamable HTTP transport as Django views (rejected —
  reimplements the SDK).

### Decision: ASGI composition
Add `organizer/asgi.py` as a small ASGI router: requests to `/mcp` and to the protected-resource
well-known paths go to the MCP Starlette app; everything else goes to Django's ASGI app. The MCP
app's lifespan runs the session manager. `ASGI_APPLICATION` is set; dev/prod run
`uvicorn organizer.asgi:application`. The existing WSGI entrypoint still serves the REST API for
deployments that don't need MCP.

### Decision: Discovery + Dynamic Client Registration
- Protected Resource Metadata (RFC 9728) is served at `/.well-known/oauth-protected-resource`
  (and the `/mcp`-suffixed variant), advertising this resource and the AS.
- Authorization Server Metadata (RFC 8414) is served by DOT (or a thin view if the installed DOT
  version lacks it) at `/.well-known/oauth-authorization-server`, advertising `registration_endpoint`.
- Dynamic Client Registration (RFC 7591): use DOT's built-in endpoint if the installed version
  provides it; otherwise add a thin registration view that creates a public, authorization-code,
  PKCE `Application` from the client's `redirect_uris` and returns `client_id`. This lets Claude
  self-register without the user hand-creating an OAuth app.

### Decision: Tool surface (full CRUD), reusing serializers
Tools mirror the REST resources. Reads use the list/detail serializers and `TaskFilterSet`; writes
run the serializer's validation then `.save(owner=user)` for tasks. Owner scoping matches
`TaskItemViewSet` (tasks filtered to `request.user`); comments record the authenticated user.
- Tasks: `list_tasks` (filters: search/`contains`, status, priority, completed, tags, project,
  for_today, today_view, pagination), `get_task`, `create_task`, `update_task`, `delete_task`.
- Projects: `list_projects`, `get_project`, `create_project`, `update_project`, `delete_project`.
- Tags: `list_tags`, `get_tag`, `create_tag`, `update_tag`, `delete_tag`.
- Comments: `list_task_comments`, `add_task_comment`, `delete_task_comment`.

## Risks / Trade-offs
- **ASGI operational change** → keep WSGI working for the REST API; document uvicorn for MCP. Django
  admin/DRF run fine under ASGI.
- **Library API drift** (exact DOT DCR/metadata + MCP SDK auth hooks vary by version) → pin versions
  in `uv.lock`, and verify the installed APIs during implementation; fall back to thin local views
  for any metadata/DCR endpoint the pinned DOT lacks.
- **Sync ORM under async transport** → the SDK runs tool handlers such that blocking ORM calls are
  offloaded (`sync_to_async` / worker thread) to avoid blocking the event loop.
- **Token leakage / over-broad grant** → short-lived access tokens + refresh, `read`/`write` scopes,
  per-user revocation via DOT; deletes remain explicit tools the client can gate behind confirmation.

## Migration Plan
1. Add deps, settings, and `oauth2_provider` migrations (`migrate`).
2. Land the MCP package + ASGI router behind the new `/mcp` path (no impact on existing routes).
3. Regenerate `requirements.txt`. Document uvicorn run + client setup in `CLAUDE.md`.
Rollback: remove the `/mcp` mount and `oauth2_provider` from `INSTALLED_APPS`; the REST API is
unaffected. (Toolkit tables can be left in place or dropped.)

## Open Questions
- Final scope granularity (single `mcp` scope vs `read`/`write`) — starting with `read`/`write`.
- Whether to also expose the scoutfile-federated users through MCP (out of scope for v1; owner-based).
