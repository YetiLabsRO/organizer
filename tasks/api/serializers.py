from dj_rest_auth.serializers import TokenSerializer
from rest_framework import serializers
from rest_framework.authtoken.models import Token
from rest_framework.relations import PrimaryKeyRelatedField

from tasks.models import Project, Tag, TaskComment, TaskItem

__author__ = 'andrei'


class TaskCommentSerializer(serializers.ModelSerializer):
    class Meta:
        model = TaskComment
        fields = ("id", "description", "user", "timestamp")


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
        fields = ("id", "title", "description", "start_date", "end_date", "estimated_time", "parent_task", "status",
                  "owner", "priority", "completed", "tags", "completed_date", "changed_date", "order", "project",
                  "comments", "for_today")

    tags = PrimaryKeyRelatedField(queryset=Tag.objects.all(), many=True, allow_null=True, required=False)
    # Owner is set server-side from the request user (see TaskItemViewSet.perform_create); clients
    # cannot assign or reassign it.
    owner = PrimaryKeyRelatedField(read_only=True)
    comments = TaskCommentSerializer(many=True, read_only=True)


class TaskListSerializer(serializers.ModelSerializer):
    """Lightweight serializer for the (windowed) task list — omits nested comments.

    Comments are only rendered on the detail view, which uses ``TaskSerializer``.
    """

    class Meta:
        model = TaskItem
        fields = ("id", "title", "description", "start_date", "end_date", "estimated_time", "parent_task", "status",
                  "owner", "priority", "completed", "tags", "completed_date", "changed_date", "order", "project",
                  "for_today")

    tags = PrimaryKeyRelatedField(queryset=Tag.objects.all(), many=True, allow_null=True, required=False)
    owner = PrimaryKeyRelatedField(read_only=True)


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
        fields = ('key', 'user', 'role')

    user = serializers.SerializerMethodField("user_username")
    role = serializers.SerializerMethodField("user_role")

    def user_username(self, obj):
        return obj.user.username

    def user_role(self, obj):
        #   TODO: implement roles
        return "admin"

