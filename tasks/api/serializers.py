from dj_rest_auth.serializers import TokenSerializer
from rest_framework import serializers
from rest_framework.authtoken.models import Token
from rest_framework.relations import PrimaryKeyRelatedField

from tasks.models import Project, Tag, TaskComment, TaskItem

__author__ = "andrei"


class TaskCommentSerializer(serializers.ModelSerializer):
    class Meta:
        model = TaskComment
        fields = ("id", "task", "description", "user", "user_username", "timestamp")

    # Author is set server-side from the request user (see TaskCommentViewSet.perform_create);
    # clients POST only `task` + `description`. `user_username` is a read-only display convenience.
    user = PrimaryKeyRelatedField(read_only=True)
    user_username = serializers.CharField(source="user.username", read_only=True)


class TagBaseSerializer(serializers.ModelSerializer):
    class Meta:
        model = Tag
        fields = ("id", "name", "color", "slug")

    id = serializers.IntegerField(read_only=False, required=False)


class TagSerializer(TagBaseSerializer):
    class Meta:
        model = Tag
        fields = ("id", "slug", "name", "description", "color", "count")

    count = serializers.SerializerMethodField()

    def get_count(self, obj):
        return obj.tasks.count()


class TaskSerializer(serializers.ModelSerializer):
    class Meta:
        model = TaskItem
        fields = (
            "id",
            "title",
            "description",
            "start_date",
            "end_date",
            "estimated_time",
            "parent_task",
            "parent_task_title",
            "status",
            "owner",
            "priority",
            "completed",
            "tags",
            "completed_date",
            "created_date",
            "changed_date",
            "order",
            "project",
            "comments",
            "for_today",
            "template",
            "template_title",
        )

    tags = PrimaryKeyRelatedField(queryset=Tag.objects.all(), many=True, allow_null=True, required=False)
    # Owner is set server-side from the request user (see TaskItemViewSet.perform_create); clients
    # cannot assign or reassign it.
    owner = PrimaryKeyRelatedField(read_only=True)
    comments = TaskCommentSerializer(many=True, read_only=True)
    # Read-only context for the detail view: the recurring template that spawned this task and the
    # parent task, surfaced as titles so the UI can render a badge/link without a second fetch.
    template = PrimaryKeyRelatedField(read_only=True)
    template_title = serializers.CharField(source="template.title", read_only=True, default=None)
    parent_task_title = serializers.CharField(source="parent_task.title", read_only=True, default=None)


class TaskListSerializer(serializers.ModelSerializer):
    """Lightweight serializer for the (windowed) task list — omits nested comments.

    Comments are only rendered on the detail view, which uses ``TaskSerializer``.
    """

    class Meta:
        model = TaskItem
        fields = (
            "id",
            "title",
            "description",
            "start_date",
            "end_date",
            "estimated_time",
            "parent_task",
            "status",
            "owner",
            "priority",
            "completed",
            "tags",
            "completed_date",
            "changed_date",
            "order",
            "project",
            "for_today",
            "template",
            "template_title",
        )

    tags = PrimaryKeyRelatedField(queryset=Tag.objects.all(), many=True, allow_null=True, required=False)
    owner = PrimaryKeyRelatedField(read_only=True)
    # Lets the list mark tasks generated from a recurring template (see add-recurring-tasks).
    template = PrimaryKeyRelatedField(read_only=True)
    template_title = serializers.CharField(source="template.title", read_only=True, default=None)


class ProjectSerializer(serializers.ModelSerializer):
    class Meta:
        model = Project
        fields = ("id", "slug", "title", "description", "start_date", "end_date", "tags")

    # tasks = TaskSerializer(many=True, read_only=True)
    # slug = serializers.ReadOnlyField()
    start_date = serializers.DateTimeField(required=False, format="%d/%m/%Y")
    end_date = serializers.DateTimeField(required=False, format="%d/%m/%Y")


class UserTokenSerializer(TokenSerializer):
    class Meta:
        model = Token
        fields = ("key", "user", "role")

    user = serializers.SerializerMethodField("user_username")
    role = serializers.SerializerMethodField("user_role")

    def user_username(self, obj):
        return obj.user.username

    def user_role(self, obj):
        #   TODO: implement roles
        return "admin"
