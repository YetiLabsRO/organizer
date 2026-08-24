"""API surface for linking, provisioning and syncing Notion.

The one unusual view here is :func:`callback`. Every other endpoint is DRF and authenticates with
the SPA's token header, but the OAuth callback is a plain browser navigation carrying neither that
header nor a session cookie — so it is a bare Django view that recovers the user from the
single-use ``state`` recorded when the flow started.
"""

import logging

from django.conf import settings
from django.db import transaction
from django.shortcuts import redirect
from django.views.decorators.http import require_GET
from rest_framework import status as http_status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from integrations.notion import oauth, schema
from integrations.notion.client import NotionClient
from integrations.notion.exceptions import NotionError
from integrations.notion.models import NotionConnection, NotionOAuthFlow
from integrations.notion.serializers import (
    NotionConnectionSerializer,
    NotionPageSerializer,
    ProvisionRequestSerializer,
)
from integrations.notion.tasks import bootstrap_connection, sync_one
from tasks.models import TaskItem

logger = logging.getLogger(__name__)


def _connection_state(user):
    """The payload behind every status response."""
    connection = NotionConnection.objects.filter(user=user).select_related("database").first()
    if connection is None:
        return {"connected": False, "configured": oauth.is_configured()}

    database = getattr(connection, "database", None)
    payload = {
        "connected": True,
        "configured": oauth.is_configured(),
        "status": connection.status,
        "status_display": connection.get_status_display(),
        "workspace_name": connection.workspace_name,
        "workspace_icon": connection.workspace_icon,
        "can_refresh": connection.can_refresh,
        "last_error": connection.last_error,
        "connected_at": connection.connected_at,
        "last_synced_at": connection.last_synced_at,
        "provisioned": database is not None,
    }
    if database is not None:
        payload |= {
            "database_url": database.url,
            "bootstrap_state": database.bootstrap_state,
            "bootstrap_done": database.links.count(),
            "bootstrap_total": TaskItem.objects.filter(owner=user).count(),
        }
    return payload


class NotionStatusView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        return Response(NotionConnectionSerializer(_connection_state(request.user)).data)


class NotionConnectView(APIView):
    """Start the OAuth flow: record who is connecting, hand the SPA the URL to navigate to."""

    permission_classes = [IsAuthenticated]

    def post(self, request):
        if not oauth.is_configured():
            return Response(
                {"detail": "Notion sync is not configured on this server."},
                status=http_status.HTTP_503_SERVICE_UNAVAILABLE,
            )
        NotionOAuthFlow.purge_expired()
        state = oauth.generate_state()
        NotionOAuthFlow.objects.create(state=state, user=request.user)
        return Response({"authorize_url": oauth.build_authorize_url(state)})


class NotionDisconnectView(APIView):
    """Forget the workspace.

    Notion exposes no token revocation endpoint, so the credentials are simply destroyed here and
    the UI tells the user to remove the connection in Notion to fully revoke access.
    """

    permission_classes = [IsAuthenticated]

    def post(self, request):
        NotionConnection.objects.filter(user=request.user).delete()
        return Response({"connected": False, "configured": oauth.is_configured()})


class NotionPagesView(APIView):
    """Pages the user shared with the integration — the candidates for the database's parent."""

    permission_classes = [IsAuthenticated]

    def get(self, request):
        connection = NotionConnection.objects.filter(user=request.user).first()
        if connection is None:
            return Response({"detail": "Notion is not connected."}, status=http_status.HTTP_400_BAD_REQUEST)
        try:
            with NotionClient(connection) as client:
                pages = client.search_pages()
        except NotionError as exc:
            return Response({"detail": str(exc)}, status=http_status.HTTP_502_BAD_GATEWAY)

        payload = [
            {"id": page["id"], "title": schema.page_title(page), "url": page.get("url", "")}
            for page in pages
            # Only a page can parent a database; a data-source row cannot.
            if (page.get("parent") or {}).get("type") != "data_source_id"
        ]
        return Response(NotionPageSerializer(payload, many=True).data)


class NotionProvisionView(APIView):
    """Create the (empty) task database under a page the user picked, then start the bootstrap."""

    permission_classes = [IsAuthenticated]

    def post(self, request):
        connection = NotionConnection.objects.filter(user=request.user).select_related("database").first()
        if connection is None:
            return Response({"detail": "Notion is not connected."}, status=http_status.HTTP_400_BAD_REQUEST)
        if getattr(connection, "database", None) is not None:
            return Response(
                {"detail": "A Notion database has already been created for this account."},
                status=http_status.HTTP_409_CONFLICT,
            )

        form = ProvisionRequestSerializer(data=request.data)
        form.is_valid(raise_exception=True)

        try:
            with NotionClient(connection) as client:
                database = schema.provision(client, connection, form.validated_data["parent_page_id"])
                with transaction.atomic():
                    database.save()
                    connection.status = connection.ACTIVE
                    connection.last_error = ""
                    connection.save(update_fields=["status", "last_error"])
        except NotionError as exc:
            logger.warning("Notion provisioning failed for %s: %s", request.user, exc)
            return Response({"detail": str(exc)}, status=http_status.HTTP_502_BAD_GATEWAY)

        # The upload of existing tasks is paced at ~3 requests/second, so it never runs inline.
        bootstrap_connection.delay(connection.pk)
        return Response(NotionConnectionSerializer(_connection_state(request.user)).data)


class NotionSyncView(APIView):
    """Sync now — enqueued, never inline."""

    permission_classes = [IsAuthenticated]

    def post(self, request):
        connection = NotionConnection.objects.filter(user=request.user).select_related("database").first()
        if connection is None or getattr(connection, "database", None) is None:
            return Response(
                {"detail": "Connect Notion and create the database first."},
                status=http_status.HTTP_400_BAD_REQUEST,
            )
        sync_one.delay(connection.pk, full=bool(request.data.get("full")))
        return Response({"queued": True})


@require_GET
def callback(request):
    """Where Notion sends the browser back.

    Unauthenticated by necessity — the identity comes from ``state``, which is why that value is
    unguessable, single-use and short-lived.
    """
    redirect_base = f"{settings.FRONTEND_BASE_URL}/settings/integrations"

    error = request.GET.get("error")
    if error:
        return redirect(f"{redirect_base}?notion=error&reason={error}")

    user = NotionOAuthFlow.consume(request.GET.get("state", ""))
    if user is None:
        # Unknown, expired or replayed — all indistinguishable to the caller, on purpose.
        return redirect(f"{redirect_base}?notion=error&reason=invalid_state")

    code = request.GET.get("code", "")
    if not code:
        return redirect(f"{redirect_base}?notion=error&reason=missing_code")

    try:
        data = oauth.exchange_code(code)
    except NotionError as exc:
        logger.warning("Notion code exchange failed for %s: %s", user, exc)
        return redirect(f"{redirect_base}?notion=error&reason=exchange_failed")

    connection, _ = NotionConnection.objects.get_or_create(user=user)
    oauth.apply_token_response(connection, data, save=True)
    return redirect(f"{redirect_base}?notion=connected")
