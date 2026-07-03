"""Aggregation helpers for the task statistics endpoint (`GET /api/task/stats/`).

Every helper takes an already-filtered, owner-scoped ``TaskItem`` queryset (see
``TaskItemViewSet.stats``) so the statistics always honour the exact same filters as the task list.

Semantics:
- ``tag_distribution`` / ``status_breakdown`` / ``priority_breakdown`` reflect the filtered set as-is.
- The time-based sections restrict to solved tasks (``completed=True`` with a ``completed_date``),
  because "solved over time" is only meaningful for solved tasks.
- Per-tag sections join the M2M ``tags``, so a task carrying several tags is counted once *per tag*
  (its contribution to the per-tag series legitimately exceeds the single-count timeline total).
"""

from django.db.models import Avg, Count, DurationField, ExpressionWrapper, F
from django.db.models.functions import TruncDay, TruncWeek
from django.utils import timezone

from tasks.models import TaskItem

BUCKETS = {"day": TruncDay, "week": TruncWeek}
VALID_BUCKETS = frozenset(BUCKETS)


def _iso(value):
    """Render a Trunc* result (aware datetime) or a date as an ISO ``YYYY-MM-DD`` string."""
    if value is None:
        return None
    return value.date().isoformat() if hasattr(value, "date") else value.isoformat()


def _tag_distribution(base):
    rows = base.values("tags__slug", "tags__name", "tags__color").annotate(count=Count("id")).order_by("-count")
    return [
        {"slug": r["tags__slug"], "name": r["tags__name"], "color": r["tags__color"], "count": r["count"]} for r in rows
    ]


def _solved_timeline(done, trunc):
    rows = done.annotate(period=trunc("completed_date")).values("period").annotate(count=Count("id")).order_by("period")
    return [{"period": _iso(r["period"]), "count": r["count"]} for r in rows]


def _solved_by_tag_timeline(done, trunc):
    rows = (
        done.annotate(period=trunc("completed_date"))
        .values("period", "tags__slug", "tags__name", "tags__color")
        .annotate(count=Count("id"))
        .order_by("period")
    )
    periods = sorted({_iso(r["period"]) for r in rows})
    series_by_slug = {}
    for r in rows:
        slug = r["tags__slug"]
        series = series_by_slug.setdefault(
            slug,
            {"slug": slug, "name": r["tags__name"], "color": r["tags__color"], "_counts": {}},
        )
        series["_counts"][_iso(r["period"])] = r["count"]
    series = [
        {
            "slug": s["slug"],
            "name": s["name"],
            "color": s["color"],
            "counts": [s["_counts"].get(p, 0) for p in periods],
        }
        for s in series_by_slug.values()
    ]
    return {"periods": periods, "series": series}


def _created_vs_completed_timeline(base, done, trunc):
    created = {
        _iso(r["period"]): r["count"]
        for r in base.annotate(period=trunc("created_date")).values("period").annotate(count=Count("id"))
    }
    completed = {
        _iso(r["period"]): r["count"]
        for r in done.annotate(period=trunc("completed_date")).values("period").annotate(count=Count("id"))
    }
    return [
        {"period": p, "created": created.get(p, 0), "completed": completed.get(p, 0)}
        for p in sorted(set(created) | set(completed))
    ]


def _status_breakdown(base):
    labels = dict(TaskItem.TAKSITEM_STATUSES)
    rows = base.values("status").annotate(count=Count("id")).order_by("-count")
    return [{"status": r["status"], "label": labels.get(r["status"], r["status"]), "count": r["count"]} for r in rows]


def _priority_breakdown(base):
    labels = dict(TaskItem.TASKITEM_PRIORITIES)
    rows = base.values("priority").annotate(count=Count("id")).order_by("-priority")
    return [
        {"priority": r["priority"], "label": labels.get(r["priority"], str(r["priority"])), "count": r["count"]}
        for r in rows
    ]


def _calendar_heatmap(done, tzinfo):
    rows = (
        done.annotate(day=TruncDay("completed_date", tzinfo=tzinfo))
        .values("day")
        .annotate(count=Count("id"))
        .order_by("day")
    )
    return [{"date": _iso(r["day"]), "count": r["count"]} for r in rows]


def _time_to_completion_by_tag(done):
    delta = ExpressionWrapper(F("completed_date") - F("created_date"), output_field=DurationField())
    rows = (
        done.annotate(delta=delta)
        .values("tags__slug", "tags__name", "tags__color")
        .annotate(avg=Avg("delta"), count=Count("id"))
        .order_by("-avg")
    )
    result = []
    for r in rows:
        avg = r["avg"]
        result.append(
            {
                "slug": r["tags__slug"],
                "name": r["tags__name"],
                "color": r["tags__color"],
                "avg_days": round(avg.total_seconds() / 86400, 2) if avg else None,
                "count": r["count"],
            }
        )
    return result


def build_task_stats(base, bucket="day"):
    """Assemble the full statistics payload for a filtered ``TaskItem`` queryset.

    ``base`` must be a clean queryset (e.g. ``TaskItem.objects.filter(id__in=ids)``) so the M2M/OR
    joins introduced by the task filters do not distort the aggregations.
    """
    tzinfo = timezone.get_current_timezone()
    trunc_cls = BUCKETS[bucket]

    def trunc(field):
        return trunc_cls(field, tzinfo=tzinfo)

    done = base.filter(completed=True, completed_date__isnull=False)
    total = base.count()
    completed = base.filter(completed=True).count()

    return {
        "bucket": bucket,
        "totals": {"total": total, "completed": completed, "open": total - completed},
        "tag_distribution": _tag_distribution(base),
        "solved_timeline": _solved_timeline(done, trunc),
        "solved_by_tag_timeline": _solved_by_tag_timeline(done, trunc),
        "created_vs_completed_timeline": _created_vs_completed_timeline(base, done, trunc),
        "status_breakdown": _status_breakdown(base),
        "priority_breakdown": _priority_breakdown(base),
        "calendar_heatmap": _calendar_heatmap(done, tzinfo),
        "time_to_completion_by_tag": _time_to_completion_by_tag(done),
    }
