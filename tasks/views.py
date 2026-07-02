# Create your views here.
from django.views.generic.base import TemplateView
from rest_framework import permissions, viewsets

from tasks.api.serializers import ProjectSerializer, TagSerializer, TaskCommentSerializer, TaskSerializer
from tasks.filters import TaskFilterSet
from tasks.models import Project, Tag, TaskComment, TaskItem


class MainAppView(TemplateView):
    template_name = "tasks/index.html"

    def dispatch(self, request, *args, **kwargs):
        return super().dispatch(request, *args, **kwargs)


class TaskItemViewSet(viewsets.ModelViewSet):
    queryset = TaskItem.objects.all()
    serializer_class = TaskSerializer
    filterset_class = TaskFilterSet


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
