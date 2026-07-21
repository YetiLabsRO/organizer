from channels.routing import URLRouter
from django.urls import path

from tasks.consumers import TaskEventsConsumer

websocket_urlpatterns = [
    path("ws/tasks/", TaskEventsConsumer.as_asgi()),
]

# Composed into organizer/asgi.py for non-MCP `websocket` scopes under /ws/. A bare URLRouter — not a
# ProtocolTypeRouter — so the MCP app keeps ownership of the ASGI `lifespan` scope.
websocket_application = URLRouter(websocket_urlpatterns)
