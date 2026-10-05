"""URLs for the VolunHub integration.

Split in two on purpose, like Notion's: the DRF endpoints under ``/api/`` authenticate with the
SPA's token header, while the OAuth callback is a plain browser navigation and lives outside
``/api/`` (already excluded from the service worker by the ``/integrations/**`` rule).
"""

from django.urls import path

from integrations.volunhub import views

app_name = "volunhub"

# Mounted under /api/integrations/volunhub/
api_urlpatterns = [
    path("status/", views.VolunHubStatusView.as_view(), name="status"),
    path("connect/", views.VolunHubConnectView.as_view(), name="connect"),
    path("disconnect/", views.VolunHubDisconnectView.as_view(), name="disconnect"),
    path("sync/", views.VolunHubSyncView.as_view(), name="sync"),
    path("projects/", views.VolunHubProjectsView.as_view(), name="projects"),
    path("projects/<int:external_id>/merge/", views.VolunHubProjectMergeView.as_view(), name="project-merge"),
]

# Mounted at /integrations/volunhub/ — the redirect URI declared at client registration.
browser_urlpatterns = [
    path("callback/", views.callback, name="callback"),
]
