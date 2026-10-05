"""Serializers for the VolunHub integration's API surface. Never exposes a token."""

from rest_framework import serializers


class VolunHubConnectionSerializer(serializers.Serializer):
    """The connection as the SPA sees it."""

    connected = serializers.BooleanField()
    configured = serializers.BooleanField()
    base_url = serializers.CharField(allow_blank=True)
    status = serializers.CharField(required=False)
    status_display = serializers.CharField(required=False)
    can_write = serializers.BooleanField(required=False)
    content_push_enabled = serializers.BooleanField(required=False)
    last_error = serializers.CharField(required=False, allow_blank=True)
    connected_at = serializers.DateTimeField(required=False, allow_null=True)
    last_synced_at = serializers.DateTimeField(required=False, allow_null=True)
    linked_tasks = serializers.IntegerField(required=False)
    removed_tasks = serializers.IntegerField(required=False)
    task_errors = serializers.IntegerField(required=False)


class VolunHubProjectLinkSerializer(serializers.Serializer):
    external_id = serializers.IntegerField()
    external_name = serializers.CharField(allow_blank=True)
    external_slug = serializers.CharField(allow_blank=True)
    auto_created = serializers.BooleanField()
    project_id = serializers.IntegerField(allow_null=True)
    project_title = serializers.CharField(allow_null=True)


class MergeRequestSerializer(serializers.Serializer):
    project_id = serializers.IntegerField()


class SyncRequestSerializer(serializers.Serializer):
    retry_content = serializers.BooleanField(required=False, default=False)
