# Create your views here.
from django.views.generic.base import TemplateView
from rest_framework import permissions, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.response import Response

from tasks import recurrence
from tasks.api.serializers import (
    ProjectSerializer,
    TagSerializer,
    TaskCommentSerializer,
    TaskListSerializer,
    TaskSerializer,
    TaskTemplateSerializer,
)
from tasks.api.stats import VALID_BUCKETS, build_focus_counts, build_task_stats
from tasks.filters import TaskFilterSet
from tasks.models import Project, Tag, TaskComment, TaskItem, TaskTemplate
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

    @action(detail=False, methods=["get"], url_path="stats")
    def stats(self, request):
        """Aggregated statistics over the same filtered, owner-scoped task set as the list.

        Reuses ``TaskFilterSet`` via ``filter_queryset``; aggregates off a clean ``id__in`` queryset
        so the M2M/OR joins in the filters do not distort counts. ``?bucket=day|week`` (default
        ``day``) selects the time grouping for the timeline sections.
        """
        bucket = request.query_params.get("bucket", "day")
        if bucket not in VALID_BUCKETS:
            raise ValidationError({"bucket": f"Must be one of {sorted(VALID_BUCKETS)}."})

        filtered = self.filter_queryset(self.get_queryset())
        ids = list(filtered.values_list("id", flat=True).distinct())
        base = TaskItem.objects.filter(id__in=ids)
        return Response(build_task_stats(base, bucket))

    @action(detail=False, methods=["get"], url_path="focus-counts")
    def focus_counts(self, request):
        """Exact priority-band counts over the same filtered, owner-scoped set as the list.

        The Priority Focus page renders a *window* of the list (see ``TaskLimitOffsetPagination``),
        so counting the fetched rows client-side under-reports once the set exceeds one page. This
        aggregates the whole set in a single query instead. Same ``id__in`` indirection as ``stats``
        so the M2M/OR joins in the filters cannot distort the counts.
        """
        filtered = self.filter_queryset(self.get_queryset())
        ids = list(filtered.values_list("id", flat=True).distinct())
        base = TaskItem.objects.filter(id__in=ids)
        return Response(build_focus_counts(base))


class TaskTemplateViewSet(viewsets.ModelViewSet):
    queryset = TaskTemplate.objects.all()
    serializer_class = TaskTemplateSerializer

    def get_queryset(self):
        # Owner-scoped, like tasks — a personal organizer only shows your own templates.
        return super().get_queryset().filter(owner=self.request.user)

    def perform_create(self, serializer):
        serializer.save(owner=self.request.user)

    @action(detail=True, methods=["post"], url_path="run")
    def run(self, request, pk=None):
        """Generate this template's currently-due task immediately.

        An explicit manual action, so it overrides ``skip_if_previous_open``. Returns the created
        task (201) or 200 with ``{"detail": ...}`` when nothing is currently due.
        """
        template = self.get_object()
        task = recurrence.materialize_due_tasks(template, ignore_skip_if_open=True)
        if task is None:
            return Response({"detail": "Nothing due to generate for this template."})
        return Response(TaskSerializer(task).data, status=201)


class TagViewSet(viewsets.ModelViewSet):
    queryset = Tag.objects.all()
    serializer_class = TagSerializer
    filterset_fields = ("slug",)


class ProjectViewSet(viewsets.ModelViewSet):
    queryset = Project.objects.all()
    serializer_class = ProjectSerializer
    permission_classes = (permissions.IsAuthenticated,)


class TaskCommentViewSet(viewsets.ModelViewSet):
    queryset = TaskComment.objects.all()
    serializer_class = TaskCommentSerializer
    permission_classes = (permissions.IsAuthenticated,)

    def get_queryset(self):
        # Scope to comments on the requesting user's own tasks — a personal organizer never exposes
        # other users' comments.
        return super().get_queryset().filter(task__owner=self.request.user)

    def perform_create(self, serializer):
        # The comment author is always the authenticated user; commenting is only allowed on a task
        # the user owns.
        task = serializer.validated_data.get("task")
        if task is None or task.owner_id != self.request.user.id:
            raise PermissionDenied("You can only comment on your own tasks.")
        serializer.save(user=self.request.user)
