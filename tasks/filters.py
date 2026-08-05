from django.db.models import Q
from django.utils import timezone
from django_filters import rest_framework as filters

from tasks.models import Project, Tag, TaskItem


class OrLookupFilter(filters.CharFilter):
    def __init__(self, lookup_dict=None, *args, **kwargs):
        self.lookup_dict = lookup_dict
        super().__init__(*args, **kwargs)

    def filter(self, qs, value):
        if not value:
            return qs
        if self.distinct:
            qs = qs.distinct()
        lookup = Q()

        if self.lookup_dict:
            for field_name, lookup_expr in self.lookup_dict.items():
                lookup.add(Q(**{f"{field_name}__{lookup_expr}": value}), Q.OR)

            qs = self.get_method(qs)(lookup)
        return qs


class TaskFilterSet(filters.FilterSet):
    contains = OrLookupFilter(lookup_dict={
        "title": "icontains",
        "description": "icontains",
    })

    completed = filters.BooleanFilter("completed")
    status = filters.ChoiceFilter(choices=TaskItem.TAKSITEM_STATUSES)
    priority = filters.ChoiceFilter(choices=TaskItem.TASKITEM_PRIORITIES)
    completed_date = filters.DateFilter("completed_date", "date")

    # Completion-date range: powers the stats "period" selector (today / last week / last month /
    # custom / all-time). Bounds are inclusive and compared on the local date of completed_date.
    completed_after = filters.DateFilter("completed_date", "date__gte")
    completed_before = filters.DateFilter("completed_date", "date__lte")

    # Scopes the list to one project — what the project detail view lists its tasks with.
    project = filters.ModelChoiceFilter(queryset=Project.objects.all())

    # conjoined=True → AND across multiple tags (a task must carry *all* requested tags).
    tags = filters.ModelMultipleChoiceFilter(
        field_name="tags__slug",
        to_field_name="slug",
        queryset=Tag.objects.all(),
        conjoined=True,
    )

    # Combined daily view: tasks flagged for today OR completed today, in a single paginable query.
    today_view = filters.BooleanFilter(method="filter_today_view")

    def filter_today_view(self, queryset, name, value):
        if not value:
            return queryset
        today = timezone.localdate()
        return queryset.filter(Q(for_today=True) | Q(completed_date__date=today))

    class Meta:
        model = TaskItem
        fields = ["contains", "completed", "status", "priority", "tags", "project",
                  "completed_date", "completed_after", "completed_before", "owner",
                  "start_date", "end_date", "for_today", "today_view"]

