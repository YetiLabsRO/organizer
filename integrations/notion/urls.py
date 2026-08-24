"""URLs for the Notion integration.

Split in two on purpose: the DRF endpoints under ``/api/`` authenticate with the SPA's token
header, while the OAuth callback is a plain browser navigation and so lives outside ``/api/``.
"""

from django.urls import path

from integrations.notion import views

app_name = "notion"

# Mounted under /api/integrations/notion/
api_urlpatterns = [
    path("status/", views.NotionStatusView.as_view(), name="status"),
    path("connect/", views.NotionConnectView.as_view(), name="connect"),
    path("disconnect/", views.NotionDisconnectView.as_view(), name="disconnect"),
    path("pages/", views.NotionPagesView.as_view(), name="pages"),
    path("provision/", views.NotionProvisionView.as_view(), name="provision"),
    path("sync/", views.NotionSyncView.as_view(), name="sync"),
]

# Mounted at /integrations/notion/ — the redirect URI registered with Notion.
browser_urlpatterns = [
    path("callback/", views.callback, name="callback"),
]
