"""Generate due recurring tasks from active templates.

Runs the same core as the Celery beat job (``tasks.tasks.generate_recurring_tasks``) without needing
a broker — used by CI, for manual/backfill runs, and as a fallback if Redis/Celery is unavailable
(e.g. from system cron: `manage.py generate_recurring_tasks`).
"""

from datetime import date

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from tasks import recurrence
from tasks.models import TaskTemplate


class Command(BaseCommand):
    help = "Materialize due tasks for every active recurring template."

    def add_arguments(self, parser):
        parser.add_argument(
            "--date",
            dest="on_date",
            help="Run as if today were this ISO date (YYYY-MM-DD); defaults to the current local date.",
        )

    def handle(self, *args, **options):
        today = timezone.localdate()
        if options.get("on_date"):
            try:
                today = date.fromisoformat(options["on_date"])
            except ValueError as exc:
                raise CommandError(f"Invalid --date: {options['on_date']!r} (expected YYYY-MM-DD)") from exc

        created = 0
        for template in TaskTemplate.objects.filter(is_active=True):
            with transaction.atomic():
                task = recurrence.materialize_due_tasks(template, today)
            if task is not None:
                created += 1
                self.stdout.write(f"  + {task.title} (due {task.end_date.date()}) from template #{template.pk}")

        self.stdout.write(self.style.SUCCESS(f"Generated {created} task(s) for {today.isoformat()}."))
