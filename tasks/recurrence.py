"""Occurrence math and task materialization for recurring task templates.

Deliberately framework-light: every function here takes a ``TaskTemplate`` (and a plain ``date``)
and can be unit-tested without Celery or a running broker. The Celery task and the
``generate_recurring_tasks`` management command are thin wrappers around ``materialize_due_tasks``.

Recurrence is expressed with the template's structured fields. Occurrences are anchored at
``start_on`` and repeat every ``interval`` frequency-units. Weekdays use Python's convention
(0 = Monday … 6 = Sunday). ``day_of_month`` is clamped to each month's length, so day 31 lands on
Feb 28/29. The reserved ``rrule`` field is not evaluated yet.
"""

import calendar
from datetime import date, datetime, time, timedelta

from django.utils import timezone

from tasks.models import TaskItem, TaskTemplate


def _clamp_day(year: int, month: int, day: int) -> date:
    """A date in (year, month), with ``day`` clamped to that month's last valid day."""
    last = calendar.monthrange(year, month)[1]
    return date(year, month, min(day, last))


def _weekdays(template: TaskTemplate) -> list[int]:
    """The weekly weekday set, defaulting to the anchor's weekday when none is configured."""
    if template.weekdays:
        return sorted(set(template.weekdays))
    return [template.start_on.weekday()]


def _add_months(year: int, month: int, count: int) -> tuple[int, int]:
    total = year * 12 + (month - 1) + count
    return total // 12, total % 12 + 1


def first_occurrence(template: TaskTemplate) -> date | None:
    """The earliest occurrence on or after ``start_on`` (respecting ``end_on``), or None."""
    anchor = template.start_on
    n = max(template.interval, 1)
    result: date | None = None

    if template.frequency == TaskTemplate.DAILY:
        result = anchor
    elif template.frequency == TaskTemplate.WEEKLY:
        wds = _weekdays(template)
        monday = anchor - timedelta(days=anchor.weekday())
        while result is None:
            candidates = [monday + timedelta(days=wd) for wd in wds]
            valid = [d for d in candidates if d >= anchor]
            if valid:
                result = min(valid)
            else:
                monday += timedelta(days=n * 7)
    elif template.frequency == TaskTemplate.MONTHLY:
        day = template.day_of_month or anchor.day
        year, month = anchor.year, anchor.month
        while result is None:
            candidate = _clamp_day(year, month, day)
            if candidate >= anchor:
                result = candidate
            else:
                year, month = _add_months(year, month, n)
    elif template.frequency == TaskTemplate.YEARLY:
        month = template.month_of_year or anchor.month
        day = template.day_of_month or anchor.day
        year = anchor.year
        while result is None:
            candidate = _clamp_day(year, month, day)
            if candidate >= anchor:
                result = candidate
            else:
                year += n

    if result is not None and template.end_on and result > template.end_on:
        return None
    return result


def step(template: TaskTemplate, occurrence: date) -> date | None:
    """The next occurrence strictly after ``occurrence`` (respecting ``end_on``), or None."""
    n = max(template.interval, 1)
    nxt: date

    if template.frequency == TaskTemplate.DAILY:
        nxt = occurrence + timedelta(days=n)
    elif template.frequency == TaskTemplate.WEEKLY:
        wds = _weekdays(template)
        weekday = occurrence.weekday()
        later = [wd for wd in wds if wd > weekday]
        if later:
            nxt = occurrence + timedelta(days=later[0] - weekday)
        else:
            monday = occurrence - timedelta(days=weekday)
            nxt = monday + timedelta(days=n * 7 + wds[0])
    elif template.frequency == TaskTemplate.MONTHLY:
        day = template.day_of_month or template.start_on.day
        year, month = _add_months(occurrence.year, occurrence.month, n)
        nxt = _clamp_day(year, month, day)
    else:  # YEARLY
        month = template.month_of_year or template.start_on.month
        day = template.day_of_month or template.start_on.day
        nxt = _clamp_day(occurrence.year + n, month, day)

    if template.end_on and nxt > template.end_on:
        return None
    return nxt


def latest_occurrence_on_or_before(template: TaskTemplate, cutoff: date) -> date | None:
    """The greatest occurrence that is ``<= cutoff`` and ``>= start_on``, or None.

    This is the primitive the generator uses: latest-missed-only catch-up is simply "the latest
    occurrence eligible today". ``end_on`` is not applied here — the caller caps ``cutoff``.
    """
    anchor = template.start_on
    n = max(template.interval, 1)

    if cutoff < anchor:
        return None

    if template.frequency == TaskTemplate.DAILY:
        k = (cutoff - anchor).days // n
        return anchor + timedelta(days=k * n)

    if template.frequency == TaskTemplate.WEEKLY:
        wds = _weekdays(template)
        m0 = anchor - timedelta(days=anchor.weekday())
        mc = cutoff - timedelta(days=cutoff.weekday())
        delta_weeks = (mc - m0).days // 7
        if delta_weeks < 0:
            return None
        active_monday = m0 + timedelta(days=(delta_weeks // n) * n * 7)
        while active_monday >= m0:
            valid = [active_monday + timedelta(days=wd) for wd in wds]
            valid = [d for d in valid if anchor <= d <= cutoff]
            if valid:
                return max(valid)
            active_monday -= timedelta(days=n * 7)
        return None

    if template.frequency == TaskTemplate.MONTHLY:
        day = template.day_of_month or anchor.day
        anchor_i = anchor.year * 12 + (anchor.month - 1)
        cutoff_i = cutoff.year * 12 + (cutoff.month - 1)
        k = (cutoff_i - anchor_i) // n
        while k >= 0:
            year, month = _add_months(anchor.year, anchor.month, k * n)
            candidate = _clamp_day(year, month, day)
            if anchor <= candidate <= cutoff:
                return candidate
            k -= 1
        return None

    # YEARLY
    month = template.month_of_year or anchor.month
    day = template.day_of_month or anchor.day
    k = (cutoff.year - anchor.year) // n
    while k >= 0:
        candidate = _clamp_day(anchor.year + k * n, month, day)
        if anchor <= candidate <= cutoff:
            return candidate
        k -= 1
    return None


def occurrence_on_or_after(template: TaskTemplate, target: date) -> date | None:
    """The smallest occurrence ``>= target`` within the recurrence window, or None."""
    prev = latest_occurrence_on_or_before(template, target)
    if prev == target:
        result = target
    elif prev is None:
        result = first_occurrence(template)
    else:
        result = step(template, prev)
    if result is not None and template.end_on and result > template.end_on:
        return None
    return result


def next_occurrence(template: TaskTemplate, today: date | None = None) -> date | None:
    """The next occurrence a task will be generated for (for display in the API)."""
    today = today or timezone.localdate()
    base = today
    if template.last_generated_occurrence:
        base = max(base, template.last_generated_occurrence + timedelta(days=1))
    return occurrence_on_or_after(template, base)


def schedule_summary(template: TaskTemplate) -> str:
    """A short human-readable description of the recurrence rule."""
    n = max(template.interval, 1)
    freq = template.frequency

    if freq == TaskTemplate.DAILY:
        return "Every day" if n == 1 else f"Every {n} days"

    if freq == TaskTemplate.WEEKLY:
        names = [calendar.day_name[wd] for wd in _weekdays(template)]
        days = ", ".join(names)
        every = "Every week" if n == 1 else f"Every {n} weeks"
        return f"{every} on {days}"

    if freq == TaskTemplate.MONTHLY:
        day = template.day_of_month or template.start_on.day
        every = "Every month" if n == 1 else f"Every {n} months"
        return f"{every} on day {day}"

    # YEARLY
    month = template.month_of_year or template.start_on.month
    day = template.day_of_month or template.start_on.day
    every = "Every year" if n == 1 else f"Every {n} years"
    return f"{every} on {day} {calendar.month_name[month]}"


def _aware(day: date) -> datetime:
    return timezone.make_aware(datetime.combine(day, time.min), timezone.get_current_timezone())


def materialize_due_tasks(
    template: TaskTemplate, today: date | None = None, *, ignore_skip_if_open: bool = False
) -> TaskItem | None:
    """Generate the template's currently-due task, or return None if nothing is due.

    Idempotent and latest-missed-only: creates at most one task, for the most recent occurrence
    eligible today (occurrence date minus ``lead_time_days``). Honors ``skip_if_previous_open`` by
    declining to generate — and not advancing the marker — while the last generated task is open;
    ``ignore_skip_if_open`` overrides that (used by the explicit "run now" API action).
    """
    if not template.is_active:
        return None

    today = today or timezone.localdate()
    cutoff = today + timedelta(days=template.lead_time_days)
    if template.end_on and template.end_on < cutoff:
        cutoff = template.end_on

    occurrence = latest_occurrence_on_or_before(template, cutoff)
    if occurrence is None:
        return None
    if template.last_generated_occurrence and occurrence <= template.last_generated_occurrence:
        return None

    if template.skip_if_previous_open and not ignore_skip_if_open:
        last_task = template.generated_tasks.order_by("-pk").first()
        if last_task is not None and not last_task.completed:
            return None

    task = TaskItem(
        title=template.title,
        description=template.description,
        priority=template.priority,
        estimated_time=template.estimated_time,
        project=template.project,
        owner=template.owner,
        template=template,
        status=TaskItem.IDEA,
        start_date=_aware(today),
        end_date=_aware(occurrence),
    )
    task.save()
    # add() (not set()) so project tags inherited in TaskItem.save() are preserved alongside the
    # template's own tags.
    task.tags.add(*template.tags.all())

    template.last_generated_occurrence = occurrence
    template.save(update_fields=["last_generated_occurrence", "changed_date"])
    return task


def generate_all(today: date | None = None) -> list[TaskItem]:
    """Run generation across every active template. Returns the tasks created."""
    today = today or timezone.localdate()
    created: list[TaskItem] = []
    for template in TaskTemplate.objects.filter(is_active=True):
        task = materialize_due_tasks(template, today)
        if task is not None:
            created.append(task)
    return created
