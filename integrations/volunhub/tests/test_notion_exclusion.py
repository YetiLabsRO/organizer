"""VolunHub-sourced tasks never get a Notion page: each task has at most one external owner."""

from django.test import TestCase
from django.utils import timezone

from integrations.notion import sync as notion_sync
from integrations.notion.models import NotionTaskLink
from integrations.notion.tests.helpers import make_connection, make_database, make_fake
from integrations.volunhub.models import VolunHubTaskLink
from integrations.volunhub.tests.helpers import make_user
from tasks.models import TaskItem


class NotionExclusionTests(TestCase):
    def setUp(self):
        self.user = make_user()
        self.notion = make_connection(self.user)
        self.fake = make_fake()
        self.fake.now = timezone.now().replace(second=0, microsecond=0)

    def link(self, task, state=VolunHubTaskLink.ACTIVE):
        VolunHubTaskLink.objects.create(user=self.user, external_id=task.pk + 1000, task=task, state=state)

    def test_push_skips_active_and_removed_volunhub_tasks(self):
        make_database(self.notion)
        active = TaskItem.objects.create(owner=self.user, title="Synced with VolunHub")
        removed = TaskItem.objects.create(owner=self.user, title="Removed from VolunHub")
        plain = TaskItem.objects.create(owner=self.user, title="Plain")
        self.link(active)
        self.link(removed, state=VolunHubTaskLink.REMOVED)

        notion_sync.sync_connection(self.notion, client=self.fake)

        self.assertEqual(list(NotionTaskLink.objects.values_list("task", flat=True)), [plain.pk])

    def test_bootstrap_skips_volunhub_tasks(self):
        make_database(self.notion, bootstrapped=False)
        linked = TaskItem.objects.create(owner=self.user, title="From VolunHub")
        plain = TaskItem.objects.create(owner=self.user, title="Plain")
        self.link(linked)

        notion_sync.sync_connection(self.notion, client=self.fake)

        self.assertEqual(list(NotionTaskLink.objects.values_list("task", flat=True)), [plain.pk])
