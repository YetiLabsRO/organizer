from django.contrib.auth import get_user_model
from django.contrib.postgres.fields import ArrayField
from django.db import models
from django.utils.text import slugify
from model_utils.fields import MonitorField


class TaskItem(models.Model):
    IDEA = 'idea'
    BLOCKED = 'blocked'
    IN_PROGRESS = 'inprogress'
    GIVEN_UP = 'givenup'
    TAKSITEM_STATUSES = (
        (IDEA, "Idee"),
        (BLOCKED, "Blocată"),
        (IN_PROGRESS, "În lucru"),
        (GIVEN_UP, "Am renunțat")
    )

    HIGH = 4
    NORMAL = 2
    LOW = 1

    TASKITEM_PRIORITIES = (
        (HIGH, "Prioritară"),
        (NORMAL, "Neutră"),
        (LOW, "Joasă")
    )

    title = models.CharField(max_length=1024)
    description = models.TextField(null=True, blank=True)

    start_date = models.DateTimeField(null=True, blank=True)
    end_date = models.DateTimeField(null=True, blank=True)  # deadline
    completed_date = MonitorField(monitor='completed', when=[True, ], null=True, blank=True)
    estimated_time = models.IntegerField(null=True, blank=True)

    parent_task = models.ForeignKey("TaskItem", null=True, blank=True, on_delete=models.SET_NULL)

    order = models.IntegerField(default=0)

    created_date = models.DateTimeField(auto_now_add=True)
    changed_date = models.DateTimeField(auto_now=True)

    status = models.CharField(max_length=255, choices=TAKSITEM_STATUSES, default=IDEA)
    completed = models.BooleanField(default=False)
    priority = models. IntegerField(choices=TASKITEM_PRIORITIES, default=NORMAL)

    owner = models.ForeignKey(get_user_model(), null=True, blank=True, on_delete=models.CASCADE)
    tags = models.ManyToManyField("tasks.Tag", blank=True, related_name="tasks")

    project = models.ForeignKey("tasks.Project", null=True, blank=True, related_name="tasks", on_delete=models.SET_NULL)

    # The recurring template that generated this task (null for hand-created tasks). SET_NULL so
    # deleting a template keeps its generated tasks, mirroring project/parent_task above.
    template = models.ForeignKey(
        "tasks.TaskTemplate", null=True, blank=True, related_name="generated_tasks", on_delete=models.SET_NULL
    )

    for_today = models.BooleanField(default=False)

    class Meta:
        # Most-recently-changed first. `changed_date` is auto_now, so any edit/toggle floats a
        # task to the top; `-pk` is a deterministic final tiebreaker so limit/offset pages stay
        # stable (no duplicated/skipped rows across requests when changed_date ties).
        ordering = ["-changed_date", "-pk"]

    def __str__(self):
        return self.title

    def save(self, **kwargs):
        if not self.completed and self.completed_date:
            self.completed_date = None
        super().save(**kwargs)

        if self.project:
            for tag in self.project.tags.all():
                self.tags.add(tag)


class Project(models.Model):
    title = models.CharField(max_length=1024)
    description = models.TextField(null=True, blank=True)
    slug = models.SlugField()

    start_date = models.DateTimeField(null=True, blank=True)
    end_date = models.DateTimeField(null=True, blank=True)

    tags = models.ManyToManyField("tasks.Tag", blank=True)

    class Meta:
        ordering = ["-start_date"]

    def __str__(self):
        return self.title

    def save(self, **kwargs):
        if not self.slug:
            self.slug = slugify(self.title)
        super().save(**kwargs)


class Tag(models.Model):
    name = models.CharField(max_length=255)
    slug = models.SlugField(unique=True)
    # Free text so it can hold Markdown (rendered in the tag detail view).
    description = models.TextField(null=True, blank=True)
    color = models.CharField(max_length=7, default="#FFFFFF")

    def save(self, **kwargs):
        if not self.slug:
            self.slug = slugify(self.name)
        super().save(**kwargs)

    def __str__(self):
        return self.name


class TaskComment(models.Model):
    user = models.ForeignKey(get_user_model(), on_delete=models.CASCADE)
    timestamp = models.DateTimeField(auto_now=True)
    description = models.TextField(null=True, blank=True)
    task = models.ForeignKey(TaskItem, on_delete=models.CASCADE, related_name="comments")

    def __str__(self):
        return self.description


class TaskTemplate(models.Model):
    """A reusable task blueprint plus a recurrence rule.

    The scheduler (see ``tasks/recurrence.py``) materializes real ``TaskItem``s from active
    templates. Recurrence is expressed with structured fields for now; the nullable ``rrule`` column
    is reserved so a future change can move to full iCal RRULE without a breaking migration.
    """

    DAILY = "daily"
    WEEKLY = "weekly"
    MONTHLY = "monthly"
    YEARLY = "yearly"
    FREQUENCIES = (
        (DAILY, "Zilnic"),
        (WEEKLY, "Săptămânal"),
        (MONTHLY, "Lunar"),
        (YEARLY, "Anual"),
    )

    # --- Blueprint (copied onto each generated task) ---
    title = models.CharField(max_length=1024)
    description = models.TextField(null=True, blank=True)
    priority = models.IntegerField(choices=TaskItem.TASKITEM_PRIORITIES, default=TaskItem.NORMAL)
    estimated_time = models.IntegerField(null=True, blank=True)
    project = models.ForeignKey(
        "tasks.Project", null=True, blank=True, related_name="task_templates", on_delete=models.SET_NULL
    )
    tags = models.ManyToManyField("tasks.Tag", blank=True, related_name="task_templates")
    owner = models.ForeignKey(get_user_model(), on_delete=models.CASCADE, related_name="task_templates")

    # --- Recurrence rule (structured now, RRULE-ready) ---
    frequency = models.CharField(max_length=16, choices=FREQUENCIES, default=MONTHLY)
    # "Every N frequency-units" (e.g. interval=2 + weekly = every other week).
    interval = models.PositiveIntegerField(default=1)
    # Monthly/yearly: which day of the month (clamped to the month's length at generation time).
    day_of_month = models.PositiveSmallIntegerField(null=True, blank=True)
    # Weekly: which weekdays, as Python weekday ints (0 = Monday … 6 = Sunday).
    weekdays = ArrayField(models.PositiveSmallIntegerField(), null=True, blank=True)
    # Yearly: which month (1–12), combined with day_of_month.
    month_of_year = models.PositiveSmallIntegerField(null=True, blank=True)
    # Recurrence window. start_on defaults to the creation date (set in save()).
    start_on = models.DateField(null=True, blank=True)
    end_on = models.DateField(null=True, blank=True)
    # Reserved for a future iCal RRULE string; when set it takes precedence over the fields above.
    rrule = models.TextField(null=True, blank=True)

    # --- Generation controls ---
    # Create the task this many days before its due date (deadline stays the occurrence date).
    lead_time_days = models.PositiveIntegerField(default=0)
    # Don't generate the next instance while the previous generated task is still incomplete.
    skip_if_previous_open = models.BooleanField(default=False)
    is_active = models.BooleanField(default=True)
    # The most recent occurrence date already materialized; drives idempotency + latest-missed-only.
    last_generated_occurrence = models.DateField(null=True, blank=True)

    created_date = models.DateTimeField(auto_now_add=True)
    changed_date = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-changed_date", "-pk"]

    def __str__(self):
        return self.title

    def save(self, **kwargs):
        if self.start_on is None:
            from django.utils import timezone

            self.start_on = timezone.localdate()
        super().save(**kwargs)
