from django.contrib import admin
from django.urls import include, path
from rest_framework.routers import DefaultRouter

from mcp_server.oauth_views import RegisterClientView, authorization_server_metadata
from tasks.views import (
    MainAppView,
    ProjectViewSet,
    TagViewSet,
    TaskCommentViewSet,
    TaskItemViewSet,
    TaskTemplateViewSet,
)

admin.autodiscover()

router = DefaultRouter()
router.register(r'task', TaskItemViewSet)
router.register(r'template', TaskTemplateViewSet)
router.register(r'tag', TagViewSet)
router.register(r'project', ProjectViewSet)
router.register(r'comments', TaskCommentViewSet)

urlpatterns = [
    path('admin/', admin.site.urls),
    path('', MainAppView.as_view(), {}, "index"),
    path('api/', include(router.urls)),
    path('rest-auth/', include('dj_rest_auth.urls')),

    # OAuth 2.1 authorization server for the MCP endpoint (django-oauth-toolkit),
    # plus RFC 8414 metadata and RFC 7591 dynamic client registration (mcp_server/oauth_views.py).
    # The /mcp endpoint and the RFC 9728 protected-resource metadata are served by the MCP
    # ASGI app (organizer/asgi.py), not routed here.
    # The advertised issuer is host-only, so pydantic renders it with a trailing slash
    # ("https://host/"). Clients concatenate the well-known suffix onto that issuer, and RFC 8414
    # §3.1 also allows appending the resource path — so serve the same document at every URL a
    # client may build. Missing these makes AS discovery 404, and the client then falls back to
    # the MCP default endpoints (/authorize, /token) at the issuer root.
    path('.well-known/oauth-authorization-server', authorization_server_metadata, name='oauth_as_metadata'),
    path('.well-known/oauth-authorization-server/', authorization_server_metadata),
    path('.well-known/oauth-authorization-server/mcp', authorization_server_metadata),
    path('o/register/', RegisterClientView.as_view(), name='oauth_register'),
    path('o/', include('oauth2_provider.urls', namespace='oauth2_provider')),
]
