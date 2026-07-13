"""FastMCP application for the organizer, wired to the OAuth resource-server auth.

Import this only after Django is configured (``organizer/asgi.py`` does so). Building the app
constructs the FastMCP instance, registers the tools, and enables OAuth: the transport requires a
valid ``read``+``write`` token (so the advertised protected-resource metadata lists both scopes and
clients request them), and each mutating tool additionally asserts the ``write`` scope.
"""

from urllib.parse import urlparse

from django.conf import settings
from mcp.server.auth.settings import AuthSettings
from mcp.server.fastmcp import FastMCP
from mcp.server.transport_security import TransportSecuritySettings

from . import tools
from .auth import DjangoOAuthTokenVerifier


def build_mcp() -> FastMCP:
    base = settings.MCP_BASE_URL.rstrip("/")
    # FastMCP turns on DNS-rebinding protection with a *localhost-only* allow-list whenever its bind
    # host is loopback — which it always is behind a reverse proxy. We bind to 127.0.0.1 but are
    # addressed as MCP_BASE_URL, so the public Host header fails that check and every authenticated
    # request comes back 421 "Invalid Host header". Declare the host we are actually reached on.
    parsed = urlparse(base)
    public_host = parsed.netloc
    # With no explicit port, also tolerate a Host header that spells out :443 / :80.
    allowed_hosts = [public_host] if parsed.port else [public_host, f"{public_host}:*"]
    allowed_origins = [base] if parsed.port else [base, f"{base}:*"]
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
        transport_security=TransportSecuritySettings(
            allowed_hosts=allowed_hosts,
            allowed_origins=allowed_origins,
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
