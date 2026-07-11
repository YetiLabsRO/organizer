"""FastMCP application for the organizer, wired to the OAuth resource-server auth.

Import this only after Django is configured (``organizer/asgi.py`` does so). Building the app
constructs the FastMCP instance, registers the tools, and enables OAuth: the transport requires a
valid ``read``+``write`` token (so the advertised protected-resource metadata lists both scopes and
clients request them), and each mutating tool additionally asserts the ``write`` scope.
"""

from django.conf import settings
from mcp.server.auth.settings import AuthSettings
from mcp.server.fastmcp import FastMCP

from . import tools
from .auth import DjangoOAuthTokenVerifier


def build_mcp() -> FastMCP:
    base = settings.MCP_BASE_URL.rstrip("/")
    mcp = FastMCP(
        name="Organizer",
        instructions=(
            "Manage the signed-in user's personal organizer: tasks (with status, priority, dates, "
            "sub-tasks, tags, projects, and a 'for today' flag), projects, tags, and task comments."
        ),
        token_verifier=DjangoOAuthTokenVerifier(),
        auth=AuthSettings(
            issuer_url=base,
            resource_server_url=f"{base}/mcp",
            required_scopes=["read", "write"],
        ),
        stateless_http=True,
    )
    tools.register(mcp)
    return mcp


# Module-level singletons: the FastMCP instance and the Starlette ASGI app that serves the
# Streamable HTTP endpoint (/mcp) plus RFC 9728 protected-resource metadata. The app's lifespan
# runs the MCP session manager and is driven by organizer/asgi.py.
mcp = build_mcp()
mcp_app = mcp.streamable_http_app()
