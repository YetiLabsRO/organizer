"""ASGI config for the organizer project.

Composes two ASGI apps: the MCP Streamable HTTP app (``mcp_server``) serves ``/mcp`` and the RFC
9728 protected-resource metadata under ``/.well-known/oauth-protected-resource``; Django serves
everything else (REST API, admin, OAuth authorization server, and the RFC 8414 / RFC 7591
metadata). Run with ``uvicorn organizer.asgi:application``. The plain REST API still runs under
WSGI for deployments that don't need MCP.
"""

import os

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "organizer.settings")

from django.core.asgi import get_asgi_application  # noqa: E402

django_application = get_asgi_application()

# Import only after Django is configured — the MCP app imports Django models/serializers.
from mcp_server.server import mcp_app  # noqa: E402

_MCP_PREFIXES = ("/mcp", "/.well-known/oauth-protected-resource")


def _is_mcp_path(path: str) -> bool:
    return any(path == prefix or path.startswith(prefix + "/") for prefix in _MCP_PREFIXES)


async def application(scope, receive, send):
    if scope["type"] == "lifespan":
        # The MCP app owns the lifespan: it starts/stops the Streamable HTTP session manager.
        # Django's ASGI handler does not implement the lifespan protocol.
        await mcp_app(scope, receive, send)
        return

    if scope["type"] in ("http", "websocket") and _is_mcp_path(scope.get("path", "")):
        await mcp_app(scope, receive, send)
        return

    await django_application(scope, receive, send)
