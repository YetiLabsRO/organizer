from rest_framework.pagination import LimitOffsetPagination


class TaskLimitOffsetPagination(LimitOffsetPagination):
    """Limit/offset pagination for the task list.

    Maps directly onto the frontend virtual-scroll window (offset = first visible
    index, limit = window size). Returns the standard
    ``{count, next, previous, results}`` envelope.
    """

    default_limit = 50
    max_limit = 200
