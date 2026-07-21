"""ASGI config for the organizer project.

Composes three ASGI apps: the MCP Streamable HTTP app (``mcp_server``) serves ``/mcp`` and the RFC
9728 protected-resource metadata under ``/.well-known/oauth-protected-resource``; a Channels
``URLRouter`` serves the real-time task-sync WebSocket under ``/ws/``; Django serves everything else
(REST API, admin, OAuth authorization server, and the RFC 8414 / RFC 7591 metadata). Run with
``uvicorn organizer.asgi:application``. The plain REST API still runs under WSGI for deployments that
don't need MCP or live sync.

Note: ``ASGI_APPLICATION`` stays pointed at this composed callable rather than a Channels
``ProtocolTypeRouter`` on purpose — the MCP app owns the ASGI ``lifespan`` scope (it starts/stops the
Streamable HTTP session manager), and handing lifespan to Channels would break it.
"""

import os

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "organizer.settings")

from django.core.asgi import get_asgi_application  # noqa: E402

django_application = get_asgi_application()

# Import only after Django is configured — these import Django models/serializers.
from mcp_server.server import mcp_app  # noqa: E402
from tasks.routing import websocket_application  # noqa: E402

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

    if scope["type"] == "websocket" and scope.get("path", "").startswith("/ws/"):
        # Real-time task sync. Django's ASGI handler cannot serve WebSockets, so these are routed to
        # the Channels URLRouter before the Django fallback.
        await websocket_application(scope, receive, send)
        return

    await django_application(scope, receive, send)
