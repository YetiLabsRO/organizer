# Create your views here.
from django.views.generic.base import TemplateView
from rest_framework import permissions, viewsets

from tasks.api.serializers import (
    ProjectSerializer,
    TagSerializer,
    TaskCommentSerializer,
    TaskListSerializer,
    TaskSerializer,
)
from tasks.filters import TaskFilterSet
from tasks.models import Project, Tag, TaskComment, TaskItem
from tasks.pagination import TaskLimitOffsetPagination


class MainAppView(TemplateView):
    template_name = "tasks/index.html"

    def dispatch(self, request, *args, **kwargs):
        return super().dispatch(request, *args, **kwargs)


class TaskItemViewSet(viewsets.ModelViewSet):
    queryset = TaskItem.objects.all()
    serializer_class = TaskSerializer
    filterset_class = TaskFilterSet
    pagination_class = TaskLimitOffsetPagination

    def get_queryset(self):
        # Scope to the authenticated owner; a personal organizer only ever shows your own tasks.
        return super().get_queryset().filter(owner=self.request.user)

    def get_serializer_class(self):
        # The list is windowed and never renders comments — keep that payload light.
        if self.action == "list":
            return TaskListSerializer
        return super().get_serializer_class()

    def perform_create(self, serializer):
        serializer.save(owner=self.request.user)


class TagViewSet(viewsets.ModelViewSet):
    queryset = Tag.objects.all()
    serializer_class = TagSerializer
    filterset_fields = ("slug", )


class ProjectViewSet(viewsets.ModelViewSet):
    queryset = Project.objects.all()
    serializer_class = ProjectSerializer
    permission_classes = (permissions.IsAuthenticated, )


class TaskCommentViewSet(viewsets.ModelViewSet):
    queryset = TaskComment.objects.all()
    serializer_class = TaskCommentSerializer
    permission_classes = (permissions.IsAuthenticated, )
