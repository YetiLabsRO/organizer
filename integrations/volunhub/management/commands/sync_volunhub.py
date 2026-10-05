"""Run the VolunHub sync from the command line.

The manual counterpart to the beat schedule — useful when the broker is down. Mirrors
``sync_notion``. Every run is a full comparison (VolunHub has no incremental listing), so there is
no ``--full`` flag.
"""

from django.core.management.base import BaseCommand

from integrations.volunhub.models import VolunHubConnection
from integrations.volunhub.sync import sync_connection


class Command(BaseCommand):
    help = "Synchronize tasks with VolunHub for every connected user (or just one)."

    def add_arguments(self, parser):
        parser.add_argument("--user", type=int, default=None, help="Only sync this user id.")

    def handle(self, *args, **options):
        connections = VolunHubConnection.objects.select_related("user", "client")
        if options["user"] is not None:
            connections = connections.filter(user_id=options["user"])

        synced = 0
        for connection in connections:
            if connection.status == VolunHubConnection.NEEDS_REAUTH:
                self.stdout.write(f"{connection.user}: needs re-authorization, skipping")
                continue
            report = sync_connection(connection)
            synced += 1
            self.stdout.write(self.style.SUCCESS(f"{connection.user}: {report or 'no changes'}"))

        if not synced:
            self.stdout.write("No VolunHub connections to sync.")
