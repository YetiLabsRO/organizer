"""MCP tool definitions for tasks, projects, tags, and comments.

Each tool resolves the authenticated Django user from the OAuth access token (its ``subject``),
enforces the ``write`` scope on mutations, and runs the blocking ORM work in a worker thread so
the async transport is never blocked. The heavy lifting lives in ``mcp_server/service.py``.
"""

from typing import Any

from django.db import IntegrityError
from mcp.server.auth.middleware.auth_context import get_access_token
from mcp.server.fastmcp.exceptions import ToolError

from . import service
from ._dbcall import db_call


def _token():
    token = get_access_token()
    if token is None:  # RequireAuthMiddleware guarantees a token reaches the tools.
        raise ToolError("Not authenticated")
    return token


def _user_id() -> int:
    return int(_token().subject)


def _writer_id() -> int:
    token = _token()
    if "write" not in token.scopes:
        raise ToolError("This action requires the 'write' scope")
    return int(token.subject)


async def _run(fn, *args, **kwargs):
    try:
        return await db_call(fn, *args, **kwargs)
    except service.NotFound as exc:
        raise ToolError(str(exc)) from exc
    except IntegrityError as exc:
        # Surface DB constraint violations (e.g. a duplicate tag slug) without leaking internals.
        raise ToolError(f"The change conflicts with an existing record (constraint violation): {exc}") from exc
    except ValueError as exc:
        raise ToolError(str(exc)) from exc


# --- Task tools -------------------------------------------------------------------------


async def list_tasks(
    search: str | None = None,
    status: str | None = None,
    priority: int | None = None,
    completed: bool | None = None,
    tags: list[str] | None = None,
    project: int | None = None,
    for_today: bool | None = None,
    completed_on: str | None = None,
    limit: int = 50,
    offset: int = 0,
) -> dict[str, Any]:
    """List the authenticated user's tasks, most-important first, with optional filters.

    Filters: `search` matches the title or description (case-insensitive); `status` is one of
    idea, blocked, inprogress, givenup; `priority` is 4 (high), 2 (normal) or 1 (low);
    `completed` filters by completion; `tags` is a list of tag slugs; `project` is a project id;
    `for_today` selects tasks flagged for today; `completed_on` is a YYYY-MM-DD date. Returns
    `{count, limit, offset, results}`; page with `limit` (max 200) and `offset`.
    """
    return await _run(
        service.list_tasks,
        _user_id(),
        search=search,
        status=status,
        priority=priority,
        completed=completed,
        tags=tags,
        project=project,
        for_today=for_today,
        completed_on=completed_on,
        limit=limit,
        offset=offset,
    )


async def get_task(task_id: int) -> dict[str, Any]:
    """Get a single task owned by the authenticated user, including its comments."""
    return await _run(service.get_task, _user_id(), task_id)


async def create_task(
    title: str,
    description: str | None = None,
    status: str | None = None,
    priority: int | None = None,
    start_date: str | None = None,
    end_date: str | None = None,
    estimated_time: int | None = None,
    parent_task: int | None = None,
    project: int | None = None,
    tags: list[int] | None = None,
    for_today: bool | None = None,
    completed: bool | None = None,
    order: int | None = None,
) -> dict[str, Any]:
    """Create a task for the authenticated user.

    Only `title` is required. `status` is one of idea, blocked, inprogress, givenup (default
    idea); `priority` is 4/2/1 (default 2, normal); `start_date`/`end_date` are ISO-8601
    datetimes (`end_date` is the deadline); `parent_task` and `project` are ids; `tags` is a
    list of tag ids. Returns the created task.
    """
    return await _run(
        service.create_task,
        _writer_id(),
        title=title,
        description=description,
        status=status,
        priority=priority,
        start_date=start_date,
        end_date=end_date,
        estimated_time=estimated_time,
        parent_task=parent_task,
        project=project,
        tags=tags,
        for_today=for_today,
        completed=completed,
        order=order,
    )


async def update_task(
    task_id: int,
    title: str | None = None,
    description: str | None = None,
    status: str | None = None,
    priority: int | None = None,
    start_date: str | None = None,
    end_date: str | None = None,
    estimated_time: int | None = None,
    parent_task: int | None = None,
    project: int | None = None,
    tags: list[int] | None = None,
    for_today: bool | None = None,
    completed: bool | None = None,
    order: int | None = None,
) -> dict[str, Any]:
    """Update fields of one of the authenticated user's tasks. Omitted fields are left unchanged.

    Set `completed` to true to mark the task done (its completion timestamp is recorded) or
    false to reopen it. Field meanings match `create_task`. Returns the updated task.
    """
    return await _run(
        service.update_task,
        _writer_id(),
        task_id,
        title=title,
        description=description,
        status=status,
        priority=priority,
        start_date=start_date,
        end_date=end_date,
        estimated_time=estimated_time,
        parent_task=parent_task,
        project=project,
        tags=tags,
        for_today=for_today,
        completed=completed,
        order=order,
    )


async def delete_task(task_id: int) -> dict[str, Any]:
    """Permanently delete one of the authenticated user's tasks."""
    return await _run(service.delete_task, _writer_id(), task_id)


# --- Project tools ----------------------------------------------------------------------


async def list_projects(limit: int = 100, offset: int = 0) -> dict[str, Any]:
    """List projects with `{count, limit, offset, results}` pagination."""
    _user_id()
    return await _run(service.list_projects, limit=limit, offset=offset)


async def get_project(project_id: int) -> dict[str, Any]:
    """Get a single project by id."""
    _user_id()
    return await _run(service.get_project, project_id)


async def create_project(
    title: str,
    description: str | None = None,
    start_date: str | None = None,
    end_date: str | None = None,
    tags: list[int] | None = None,
) -> dict[str, Any]:
    """Create a project. Only `title` is required; a slug is generated from it. `tags` is a list
    of tag ids; dates are ISO-8601. Returns the created project."""
    _writer_id()
    return await _run(
        service.create_project,
        title=title,
        description=description,
        start_date=start_date,
        end_date=end_date,
        tags=tags,
    )


async def update_project(
    project_id: int,
    title: str | None = None,
    description: str | None = None,
    start_date: str | None = None,
    end_date: str | None = None,
    tags: list[int] | None = None,
) -> dict[str, Any]:
    """Update a project's fields. Omitted fields are left unchanged. Returns the updated project."""
    _writer_id()
    return await _run(
        service.update_project,
        project_id,
        title=title,
        description=description,
        start_date=start_date,
        end_date=end_date,
        tags=tags,
    )


async def delete_project(project_id: int) -> dict[str, Any]:
    """Permanently delete a project. Tasks in the project are kept (their project is cleared)."""
    _writer_id()
    return await _run(service.delete_project, project_id)


# --- Tag tools --------------------------------------------------------------------------


async def list_tags(limit: int = 200, offset: int = 0) -> dict[str, Any]:
    """List tags (each with a task `count`) with `{count, limit, offset, results}` pagination."""
    _user_id()
    return await _run(service.list_tags, limit=limit, offset=offset)


async def get_tag(tag_id: int) -> dict[str, Any]:
    """Get a single tag by id."""
    _user_id()
    return await _run(service.get_tag, tag_id)


async def create_tag(
    name: str,
    description: str | None = None,
    color: str | None = None,
) -> dict[str, Any]:
    """Create a tag. Only `name` is required; a slug is generated from it. `color` is a hex string
    like `#FF8800`. Returns the created tag."""
    _writer_id()
    return await _run(service.create_tag, name=name, description=description, color=color)


async def update_tag(
    tag_id: int,
    name: str | None = None,
    description: str | None = None,
    color: str | None = None,
) -> dict[str, Any]:
    """Update a tag's fields. Omitted fields are left unchanged. Returns the updated tag."""
    _writer_id()
    return await _run(service.update_tag, tag_id, name=name, description=description, color=color)


async def delete_tag(tag_id: int) -> dict[str, Any]:
    """Permanently delete a tag."""
    _writer_id()
    return await _run(service.delete_tag, tag_id)


# --- Comment tools ----------------------------------------------------------------------


async def list_task_comments(task_id: int) -> dict[str, Any]:
    """List the comments on one of the authenticated user's tasks."""
    return await _run(service.list_task_comments, _user_id(), task_id)


async def add_task_comment(task_id: int, description: str) -> dict[str, Any]:
    """Add a comment to one of the authenticated user's tasks, authored by that user."""
    return await _run(service.add_task_comment, _writer_id(), task_id, description)


async def delete_task_comment(comment_id: int) -> dict[str, Any]:
    """Delete a comment on one of the authenticated user's tasks."""
    return await _run(service.delete_task_comment, _writer_id(), comment_id)


ALL_TOOLS = [
    list_tasks,
    get_task,
    create_task,
    update_task,
    delete_task,
    list_projects,
    get_project,
    create_project,
    update_project,
    delete_project,
    list_tags,
    get_tag,
    create_tag,
    update_tag,
    delete_tag,
    list_task_comments,
    add_task_comment,
    delete_task_comment,
]


def register(mcp) -> None:
    """Register every tool on the given FastMCP instance (name + description come from each fn)."""
    for fn in ALL_TOOLS:
        mcp.tool()(fn)
