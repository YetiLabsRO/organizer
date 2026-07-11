"""Synchronous CRUD service backing the MCP tools.

This layer reuses the existing DRF serializers (``tasks.api.serializers``) and the task
``TaskFilterSet`` so field shape, validation, and filtering stay identical to the REST API.
It is deliberately free of any MCP/async concerns so it can be unit-tested directly; the
tool layer (``mcp_server/tools.py``) wraps these callables with ``sync_to_async`` and OAuth
scope checks. Task access is scoped to the owning user, mirroring the intent of the task API.
"""

from django.utils.datastructures import MultiValueDict
from rest_framework import serializers
from rest_framework.exceptions import ValidationError as DRFValidationError

from tasks.api.serializers import ProjectSerializer, TagSerializer, TaskCommentSerializer, TaskSerializer
from tasks.filters import TaskFilterSet
from tasks.models import Project, Tag, TaskComment, TaskItem

MAX_PAGE_SIZE = 200
DEFAULT_PAGE_SIZE = 50


class TaskReprSerializer(TaskSerializer):
    """Task representation for MCP tools.

    Drops the base serializer's nested ``comments`` field (it is exposed through the dedicated
    comment tools instead, and the reverse relation is not universally named ``comments``) and
    forces ``owner`` read-only so it can only ever be set server-side from the OAuth identity.
    """

    comments = None
    owner = serializers.PrimaryKeyRelatedField(read_only=True)

    class Meta(TaskSerializer.Meta):
        fields = tuple(f for f in TaskSerializer.Meta.fields if f != "comments")


class TagReprSerializer(TagSerializer):
    """Tag serializer for MCP tools — ``slug`` is optional (the model derives it from ``name``)."""

    slug = serializers.SlugField(required=False)


class ProjectReprSerializer(ProjectSerializer):
    """Project serializer for MCP tools — ``slug`` is optional (the model derives it from ``title``)."""

    slug = serializers.SlugField(required=False)


class NotFound(ValueError):
    """Raised when a requested object does not exist or is not visible to the user."""


def _validate(serializer):
    try:
        serializer.is_valid(raise_exception=True)
    except DRFValidationError as exc:
        raise ValueError(f"Validation failed: {exc.detail}") from exc


def _strip_none(fields: dict) -> dict:
    """Drop keys whose value is ``None`` — for partial updates, omitted means "leave unchanged"."""
    return {key: value for key, value in fields.items() if value is not None}


def _b(value: bool) -> str:
    return "true" if value else "false"


def _page(limit: int, offset: int) -> tuple[int, int]:
    limit = max(1, min(int(limit), MAX_PAGE_SIZE))
    offset = max(0, int(offset))
    return limit, offset


# --- Tasks (owner-scoped) ---------------------------------------------------------------


def _owned_task(user_id: int, task_id: int) -> TaskItem:
    try:
        return TaskItem.objects.get(pk=task_id, owner_id=user_id)
    except TaskItem.DoesNotExist as exc:
        raise NotFound(f"Task {task_id} not found") from exc


def list_tasks(
    user_id: int,
    *,
    search: str | None = None,
    status: str | None = None,
    priority: int | None = None,
    completed: bool | None = None,
    tags: list[str] | None = None,
    project: int | None = None,
    for_today: bool | None = None,
    completed_on: str | None = None,
    limit: int = DEFAULT_PAGE_SIZE,
    offset: int = 0,
) -> dict:
    queryset = TaskItem.objects.filter(owner_id=user_id)
    if project is not None:
        queryset = queryset.filter(project_id=project)

    data = MultiValueDict()
    if search:
        data["contains"] = search
    if status is not None:
        data["status"] = status
    if priority is not None:
        data["priority"] = str(priority)
    if completed is not None:
        data["completed"] = _b(completed)
    if for_today is not None:
        data["for_today"] = _b(for_today)
    if completed_on is not None:
        data["completed_date"] = completed_on
    if tags:
        data.setlist("tags", list(tags))

    filterset = TaskFilterSet(data, queryset=queryset)
    if not filterset.is_valid():
        raise ValueError(f"Invalid filter(s): {filterset.errors}")

    filtered = filterset.qs
    limit, offset = _page(limit, offset)
    total = filtered.count()
    window = filtered[offset : offset + limit]
    return {
        "count": total,
        "limit": limit,
        "offset": offset,
        "results": list(TaskReprSerializer(window, many=True).data),
    }


def get_task(user_id: int, task_id: int) -> dict:
    task = _owned_task(user_id, task_id)
    data = dict(TaskReprSerializer(task).data)
    # Embed comments without depending on the reverse-relation accessor name.
    comments = TaskComment.objects.filter(task=task).order_by("timestamp")
    data["comments"] = list(TaskCommentSerializer(comments, many=True).data)
    return data


def create_task(user_id: int, **fields) -> dict:
    serializer = TaskReprSerializer(data=_strip_none(fields))
    _validate(serializer)
    task = serializer.save(owner_id=user_id)
    return dict(TaskReprSerializer(task).data)


def update_task(user_id: int, task_id: int, **fields) -> dict:
    task = _owned_task(user_id, task_id)
    serializer = TaskReprSerializer(task, data=_strip_none(fields), partial=True)
    _validate(serializer)
    serializer.save()
    return dict(TaskReprSerializer(task).data)


def delete_task(user_id: int, task_id: int) -> dict:
    _owned_task(user_id, task_id).delete()
    return {"deleted": True, "id": task_id}


# --- Projects (global, mirroring the project API) ---------------------------------------


def _project(project_id: int) -> Project:
    try:
        return Project.objects.get(pk=project_id)
    except Project.DoesNotExist as exc:
        raise NotFound(f"Project {project_id} not found") from exc


def list_projects(*, limit: int = 100, offset: int = 0) -> dict:
    queryset = Project.objects.all()
    limit, offset = _page(limit, offset)
    total = queryset.count()
    window = queryset[offset : offset + limit]
    return {
        "count": total,
        "limit": limit,
        "offset": offset,
        "results": list(ProjectReprSerializer(window, many=True).data),
    }


def get_project(project_id: int) -> dict:
    return dict(ProjectReprSerializer(_project(project_id)).data)


def create_project(**fields) -> dict:
    serializer = ProjectReprSerializer(data=_strip_none(fields))
    _validate(serializer)
    return dict(ProjectReprSerializer(serializer.save()).data)


def update_project(project_id: int, **fields) -> dict:
    project = _project(project_id)
    serializer = ProjectReprSerializer(project, data=_strip_none(fields), partial=True)
    _validate(serializer)
    serializer.save()
    return dict(ProjectReprSerializer(project).data)


def delete_project(project_id: int) -> dict:
    _project(project_id).delete()
    return {"deleted": True, "id": project_id}


# --- Tags (global, mirroring the tag API) -----------------------------------------------


def _tag(tag_id: int) -> Tag:
    try:
        return Tag.objects.get(pk=tag_id)
    except Tag.DoesNotExist as exc:
        raise NotFound(f"Tag {tag_id} not found") from exc


def list_tags(*, limit: int = 200, offset: int = 0) -> dict:
    queryset = Tag.objects.all()
    limit, offset = _page(limit, offset)
    total = queryset.count()
    window = queryset[offset : offset + limit]
    return {
        "count": total,
        "limit": limit,
        "offset": offset,
        "results": list(TagReprSerializer(window, many=True).data),
    }


def get_tag(tag_id: int) -> dict:
    return dict(TagReprSerializer(_tag(tag_id)).data)


def create_tag(**fields) -> dict:
    serializer = TagReprSerializer(data=_strip_none(fields))
    _validate(serializer)
    return dict(TagReprSerializer(serializer.save()).data)


def update_tag(tag_id: int, **fields) -> dict:
    tag = _tag(tag_id)
    serializer = TagReprSerializer(tag, data=_strip_none(fields), partial=True)
    _validate(serializer)
    serializer.save()
    return dict(TagReprSerializer(tag).data)


def delete_tag(tag_id: int) -> dict:
    _tag(tag_id).delete()
    return {"deleted": True, "id": tag_id}


# --- Task comments (scoped to the user's own tasks) -------------------------------------


def list_task_comments(user_id: int, task_id: int) -> dict:
    task = _owned_task(user_id, task_id)
    comments = TaskComment.objects.filter(task=task).order_by("timestamp")
    results = list(TaskCommentSerializer(comments, many=True).data)
    return {"count": len(results), "results": results}


def add_task_comment(user_id: int, task_id: int, description: str) -> dict:
    task = _owned_task(user_id, task_id)
    comment = TaskComment.objects.create(task=task, user_id=user_id, description=description)
    return dict(TaskCommentSerializer(comment).data)


def delete_task_comment(user_id: int, comment_id: int) -> dict:
    try:
        comment = TaskComment.objects.get(pk=comment_id, task__owner_id=user_id)
    except TaskComment.DoesNotExist as exc:
        raise NotFound(f"Comment {comment_id} not found") from exc
    comment.delete()
    return {"deleted": True, "id": comment_id}
