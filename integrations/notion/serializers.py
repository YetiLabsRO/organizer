"""Serializers for the Notion integration's API surface.

Deliberately thin, and deliberately never exposing a token: the SPA is told *about* the connection
(status, workspace, when it last synced, where the database lives) and nothing that would let it act
as the user in Notion.
"""

from rest_framework import serializers


class NotionConnectionSerializer(serializers.Serializer):
    """The connection as the SPA sees it."""

    connected = serializers.BooleanField()
    configured = serializers.BooleanField()
    status = serializers.CharField(required=False)
    status_display = serializers.CharField(required=False)
    workspace_name = serializers.CharField(required=False, allow_blank=True)
    workspace_icon = serializers.CharField(required=False, allow_blank=True)
    can_refresh = serializers.BooleanField(required=False)
    last_error = serializers.CharField(required=False, allow_blank=True)
    connected_at = serializers.DateTimeField(required=False, allow_null=True)
    last_synced_at = serializers.DateTimeField(required=False, allow_null=True)

    # Provisioning
    provisioned = serializers.BooleanField(required=False)
    database_url = serializers.CharField(required=False, allow_blank=True)
    bootstrap_state = serializers.CharField(required=False, allow_blank=True)
    bootstrap_done = serializers.IntegerField(required=False)
    bootstrap_total = serializers.IntegerField(required=False)


class NotionPageSerializer(serializers.Serializer):
    """A page the user shared with the integration, offered as a parent for the database."""

    id = serializers.CharField()
    title = serializers.CharField()
    url = serializers.CharField(allow_blank=True)


class ProvisionRequestSerializer(serializers.Serializer):
    parent_page_id = serializers.CharField(max_length=64)
