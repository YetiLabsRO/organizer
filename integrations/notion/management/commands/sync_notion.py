"""Run the Notion sync from the command line.

The manual counterpart to the beat schedule — useful when the broker is down, and the way to force
a full reconciliation without waiting for NOTION_FULL_SYNC_HOURS to elapse. Mirrors
``generate_recurring_tasks``.
"""

from django.core.management.base import BaseCommand

from integrations.notion.models import NotionConnection
from integrations.notion.sync import sync_connection


class Command(BaseCommand):
    help = "Synchronize tasks with Notion for every connected user (or just one)."

    def add_arguments(self, parser):
        parser.add_argument("--user", type=int, default=None, help="Only sync this user id.")
        parser.add_argument(
            "--full",
            action="store_true",
            help="Force a full reconciliation — the only pass that notices pages trashed in Notion.",
        )

    def handle(self, *args, **options):
        connections = NotionConnection.objects.select_related("database", "user")
        if options["user"] is not None:
            connections = connections.filter(user_id=options["user"])

        synced = 0
        for connection in connections:
            if getattr(connection, "database", None) is None:
                self.stdout.write(f"{connection.user}: no database provisioned, skipping")
                continue
            report = sync_connection(connection, full=options["full"])
            synced += 1
            self.stdout.write(self.style.SUCCESS(f"{connection.user}: {report or 'no changes'}"))

        if not synced:
            self.stdout.write("No Notion connections to sync.")
