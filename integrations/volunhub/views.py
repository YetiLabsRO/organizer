"""API surface for linking, syncing and project merging with VolunHub.

As with Notion, :func:`callback` is the odd one out: VolunHub's redirect is a plain browser
navigation carrying neither the SPA's DRF token nor a session, so it is a bare Django view that
recovers the user — and the PKCE verifier — from the single-use ``state`` recorded at connect time.
"""

import logging
from urllib.parse import urlencode

from django.conf import settings
from django.db import transaction
from django.shortcuts import redirect
from django.utils import timezone
from django.views.decorators.http import require_GET
from rest_framework import status as http_status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from integrations.volunhub import oauth
from integrations.volunhub.exceptions import VolunHubError, VolunHubScopeError
from integrations.volunhub.models import VolunHubConnection, VolunHubOAuthFlow, VolunHubTaskLink
from integrations.volunhub.projects import links_visible_to, merge_project
from integrations.volunhub.serializers import (
    MergeRequestSerializer,
    SyncRequestSerializer,
    VolunHubConnectionSerializer,
    VolunHubProjectLinkSerializer,
)
from integrations.volunhub.tasks import sync_one
from tasks.models import Project
from tasks.signals import broadcast_task_updated

logger = logging.getLogger(__name__)


def _connection_state(user):
    """The payload behind every status response."""
    base = {"configured": oauth.is_configured(), "base_url": settings.VOLUNHUB_BASE_URL}
    connection = VolunHubConnection.objects.filter(user=user).first()
    if connection is None:
        return {"connected": False, **base}

    links = VolunHubTaskLink.objects.filter(user=user, task__isnull=False)
    return {
        "connected": True,
        **base,
        "status": connection.status,
        "status_display": connection.get_status_display(),
        "can_write": connection.can_write,
        "content_push_enabled": connection.content_push_enabled,
        "last_error": connection.last_error,
        "connected_at": connection.connected_at,
        "last_synced_at": connection.last_synced_at,
        "linked_tasks": links.filter(state=VolunHubTaskLink.ACTIVE).count(),
        "removed_tasks": links.filter(state=VolunHubTaskLink.REMOVED).count(),
        "task_errors": links.exclude(last_error="").count(),
    }


def _queue_sync(connection):
    """Queue a sync after commit. A down broker must not break the request — beat will catch up."""

    def enqueue():
        try:
            sync_one.delay(connection.pk)
        except Exception:  # noqa: BLE001 - broker outages surface in logs, not as a failed request
            logger.exception("Could not queue a VolunHub sync for %s", connection.user)

    transaction.on_commit(enqueue)


class VolunHubStatusView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        return Response(VolunHubConnectionSerializer(_connection_state(request.user)).data)


class VolunHubConnectView(APIView):
    """Start the OAuth flow: register if needed, record who is connecting, return the URL to visit."""

    permission_classes = [IsAuthenticated]

    def post(self, request):
        if not oauth.is_configured():
            return Response(
                {"detail": "VolunHub sync is not configured on this server."},
                status=http_status.HTTP_503_SERVICE_UNAVAILABLE,
            )
        try:
            client = oauth.get_oauth_client()
        except VolunHubError as exc:
            logger.warning("VolunHub client registration failed: %s", exc)
            return Response({"detail": str(exc)}, status=http_status.HTTP_502_BAD_GATEWAY)

        VolunHubOAuthFlow.purge_expired()
        state, verifier = oauth.generate_state(), oauth.generate_code_verifier()
        VolunHubOAuthFlow.objects.create(state=state, code_verifier=verifier, user=request.user, client=client)
        return Response({"authorize_url": oauth.build_authorize_url(client, state, verifier)})


class VolunHubDisconnectView(APIView):
    """Revoke (best-effort) and forget the credentials. Local tasks are kept, marked disconnected.

    Task links are kept too, so reconnecting re-attaches the same local tasks instead of importing
    duplicates.
    """

    permission_classes = [IsAuthenticated]

    def post(self, request):
        connection = VolunHubConnection.objects.filter(user=request.user).select_related("client").first()
        if connection is not None:
            oauth.revoke(connection)
            with transaction.atomic():
                active = VolunHubTaskLink.objects.filter(
                    user=request.user, state=VolunHubTaskLink.ACTIVE, task__isnull=False
                ).select_related("task")
                tasks = [link.task for link in active]
                active.update(
                    state=VolunHubTaskLink.REMOVED,
                    removed_reason=VolunHubTaskLink.DISCONNECTED,
                    removed_at=timezone.now(),
                )
                connection.delete()
                for task in tasks:
                    broadcast_task_updated(task)
        return Response(VolunHubConnectionSerializer(_connection_state(request.user)).data)


class VolunHubSyncView(APIView):
    """Sync now — enqueued, never inline. ``retry_content`` re-enables a disabled content push."""

    permission_classes = [IsAuthenticated]

    def post(self, request):
        connection = VolunHubConnection.objects.filter(user=request.user).first()
        if connection is None:
            return Response({"detail": "VolunHub is not connected."}, status=http_status.HTTP_400_BAD_REQUEST)
        if connection.status == VolunHubConnection.NEEDS_REAUTH:
            return Response({"detail": "Reconnect VolunHub before syncing."}, status=http_status.HTTP_409_CONFLICT)
        form = SyncRequestSerializer(data=request.data)
        form.is_valid(raise_exception=True)
        if form.validated_data["retry_content"] and not connection.content_push_enabled:
            connection.content_push_enabled = True
            connection.last_error = ""
            connection.save(update_fields=["content_push_enabled", "last_error"])
        _queue_sync(connection)
        return Response({"queued": True})


def _project_payload(link):
    return {
        "external_id": link.external_id,
        "external_name": link.external_name,
        "external_slug": link.external_slug,
        "auto_created": link.auto_created,
        "project_id": link.project_id,
        "project_title": link.project.title if link.project is not None else None,
    }


class VolunHubProjectsView(APIView):
    """VolunHub projects the caller's tasks came from, and the local project each maps to."""

    permission_classes = [IsAuthenticated]

    def get(self, request):
        payload = [_project_payload(link) for link in links_visible_to(request.user)]
        return Response(VolunHubProjectLinkSerializer(payload, many=True).data)


class VolunHubProjectMergeView(APIView):
    """Map a VolunHub project onto an existing local project (folding in the auto-created one)."""

    permission_classes = [IsAuthenticated]

    def post(self, request, external_id):
        link = links_visible_to(request.user).filter(external_id=external_id).first()
        if link is None:
            return Response({"detail": "Unknown VolunHub project."}, status=http_status.HTTP_404_NOT_FOUND)
        form = MergeRequestSerializer(data=request.data)
        form.is_valid(raise_exception=True)
        target = Project.objects.filter(pk=form.validated_data["project_id"]).first()
        if target is None:
            return Response({"project_id": ["Unknown project."]}, status=http_status.HTTP_400_BAD_REQUEST)
        merge_project(link, target)
        link.refresh_from_db()
        return Response(VolunHubProjectLinkSerializer(_project_payload(link)).data)


@require_GET
def callback(request):
    """Where VolunHub sends the browser back.

    Unauthenticated by necessity — identity and the PKCE verifier both come from ``state``, which is
    why that value is unguessable, single-use and short-lived.
    """
    redirect_base = f"{settings.FRONTEND_BASE_URL}/settings/integrations"

    error = request.GET.get("error")
    if error:
        # Echoed from VolunHub's redirect, so encode it rather than splicing raw text into the URL.
        return redirect(f"{redirect_base}?{urlencode({'volunhub': 'error', 'reason': error[:64]})}")

    flow = VolunHubOAuthFlow.consume(request.GET.get("state", ""))
    if flow is None:
        # Unknown, expired or replayed — all indistinguishable to the caller, on purpose.
        return redirect(f"{redirect_base}?volunhub=error&reason=invalid_state")

    code = request.GET.get("code", "")
    if not code:
        return redirect(f"{redirect_base}?volunhub=error&reason=missing_code")

    try:
        data = oauth.exchange_code(flow.client, code, flow.code_verifier)
    except VolunHubError as exc:
        logger.warning("VolunHub code exchange failed for %s: %s", flow.user, exc)
        return redirect(f"{redirect_base}?volunhub=error&reason=exchange_failed")

    connection = VolunHubConnection.objects.filter(user=flow.user).first() or VolunHubConnection(user=flow.user)
    connection.client = flow.client
    try:
        oauth.apply_token_response(connection, data)
    except VolunHubScopeError as exc:
        logger.warning("VolunHub grant for %s lacks read access: %s", flow.user, exc)
        return redirect(f"{redirect_base}?volunhub=error&reason=insufficient_scope")
    # A fresh grant is also the way back from a disabled content push.
    connection.content_push_enabled = True
    connection.save()

    _queue_sync(connection)
    return redirect(f"{redirect_base}?volunhub=connected")
