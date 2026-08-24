"""The sync engine.

The tests that matter most here are the ones a plausible-looking implementation still fails:
echo suppression, the ping-pong invariant, the same-minute conflict tie, and owner scoping.
"""

from datetime import timedelta

from django.test import TestCase
from django.utils import timezone

from integrations.notion import schema, sync
from integrations.notion.models import NotionDatabase, NotionTaskLink
from integrations.notion.tests.fakes import HUMAN_ID, minute_floor
from integrations.notion.tests.helpers import make_connection, make_database, make_fake, make_user
from tasks.models import Project, Tag, TaskItem


class SyncTestCase(TestCase):
    def setUp(self):
        self.user = make_user()
        self.connection = make_connection(self.user)
        self.database = make_database(self.connection)
        self.fake = make_fake()
        self.fake.now = timezone.now().replace(second=0, microsecond=0)

    def run_sync(self, full=False):
        return sync.sync_connection(self.connection, full=full, client=self.fake)

    def make_task(self, **kwargs):
        kwargs.setdefault("owner", self.user)
        kwargs.setdefault("title", "A task")
        return TaskItem.objects.create(**kwargs)

    def human_page(self, title="From Notion", **extra):
        properties = {
            schema.TITLE: {"title": [{"type": "text", "text": {"content": title}}]},
            **extra,
        }
        return self.fake.add_page_as_human(properties)


class PushTests(SyncTestCase):
    def test_a_new_local_task_becomes_a_notion_page(self):
        task = self.make_task(title="Buy milk")

        report = self.run_sync()

        self.assertEqual(report.created_remotely, 1)
        link = NotionTaskLink.objects.get(task=task)
        page = self.fake.pages[link.notion_page_id]
        self.assertEqual(page["properties"][schema.TITLE]["title"][0]["plain_text"], "Buy milk")

    def test_a_local_edit_is_pushed(self):
        task = self.make_task(title="Original")
        self.run_sync()

        task.title = "Renamed"
        task.save()
        report = self.run_sync()

        self.assertEqual(report.pushed, 1)
        link = NotionTaskLink.objects.get(task=task)
        self.assertEqual(
            self.fake.pages[link.notion_page_id]["properties"][schema.TITLE]["title"][0]["plain_text"], "Renamed"
        )

    def test_an_unchanged_task_is_not_pushed_again(self):
        self.make_task()
        self.run_sync()

        report = self.run_sync()

        self.assertEqual(report.pushed, 0)
        self.assertEqual(report.created_remotely, 0)

    def test_deleting_a_task_trashes_its_page(self):
        task = self.make_task()
        self.run_sync()
        page_id = NotionTaskLink.objects.get(task=task).notion_page_id

        task.delete()
        # SET_NULL leaves the link behind as a tombstone holding the page id.
        self.assertTrue(NotionTaskLink.objects.filter(notion_page_id=page_id, task=None).exists())

        report = self.run_sync()

        self.assertEqual(report.trashed, 1)
        self.assertTrue(self.fake.pages[page_id]["in_trash"])
        self.assertFalse(NotionTaskLink.objects.filter(notion_page_id=page_id).exists())

    def test_parent_relations_are_written_in_a_second_pass(self):
        parent = self.make_task(title="Parent")
        child = self.make_task(title="Child", parent_task=parent)

        self.run_sync()

        parent_page = NotionTaskLink.objects.get(task=parent).notion_page_id
        child_page = NotionTaskLink.objects.get(task=child).notion_page_id
        relation = self.fake.pages[child_page]["properties"][schema.PARENT_TASK]["relation"]
        self.assertEqual([item["id"] for item in relation], [parent_page])

    def test_a_failing_page_does_not_abort_the_batch(self):
        self.make_task(title="First")
        self.make_task(title="Second")
        self.fake.fail_next = "create_page"

        report = self.run_sync()

        # One failed, the other still got through.
        self.assertEqual(report.created_remotely, 1)


class OwnerScopingTests(SyncTestCase):
    def test_another_users_task_in_a_shared_project_is_never_pushed(self):
        # Project and Tag have no owner in this app, so a project-based filter would leak.
        project = Project.objects.create(title="Shared")
        other = make_user("other")
        self.make_task(title="Mine", project=project)
        theirs = TaskItem.objects.create(owner=other, title="Theirs", project=project)

        self.run_sync()

        self.assertEqual(NotionTaskLink.objects.filter(task=theirs).count(), 0)
        titles = [page["properties"][schema.TITLE]["title"][0]["plain_text"] for page in self.fake.pages.values()]
        self.assertEqual(titles, ["Mine"])

    def test_an_ownerless_task_is_not_pushed(self):
        TaskItem.objects.create(owner=None, title="Orphan")

        self.run_sync()

        self.assertEqual(len(self.fake.pages), 0)


class PullTests(SyncTestCase):
    def test_a_page_created_in_notion_becomes_a_task(self):
        self.human_page(title="From Notion")

        report = self.run_sync()

        self.assertEqual(report.created_locally, 1)
        task = TaskItem.objects.get(title="From Notion")
        self.assertEqual(task.owner, self.user)

    def test_a_notion_edit_is_applied_locally(self):
        task = self.make_task(title="Original")
        self.run_sync()
        page_id = NotionTaskLink.objects.get(task=task).notion_page_id

        self.fake.advance(minutes=5)
        self.fake.edit_as_human(page_id, {schema.TITLE: [{"type": "text", "text": {"content": "Edited in Notion"}}]})
        self.fake.edit_as_human(
            page_id, {schema.TITLE: {"title": [{"type": "text", "text": {"content": "Edited in Notion"}}]}}
        )

        self.run_sync()

        task.refresh_from_db()
        self.assertEqual(task.title, "Edited in Notion")

    def test_the_incremental_window_overlaps_the_watermark(self):
        self.make_task()
        self.run_sync()
        self.run_sync()

        query_filters = [payload for name, payload in self.fake.calls if name == "query" and payload]
        self.assertTrue(query_filters)
        since = query_filters[-1]["last_edited_time"]["on_or_after"]
        watermark = NotionDatabase.objects.get(pk=self.database.pk).pull_watermark
        # Notion rounds last_edited_time down to the minute, so the window must reach back further.
        self.assertLess(timezone.datetime.fromisoformat(since), watermark)

    def test_full_sync_queries_without_a_filter(self):
        self.make_task()

        self.run_sync(full=True)

        self.assertTrue(any(name == "query" and payload is None for name, payload in self.fake.calls))


class EchoSuppressionTests(SyncTestCase):
    def test_our_own_write_is_not_pulled_back(self):
        task = self.make_task(title="Buy milk")
        self.run_sync()

        # The page's last editor is our bot; the next pull must ignore it.
        self.fake.advance(minutes=5)
        report = self.run_sync()

        self.assertEqual(report.skipped_echo, 0 if report.pulled == 0 else report.skipped_echo)
        task.refresh_from_db()
        self.assertEqual(task.title, "Buy milk")

    def test_a_page_last_edited_by_the_bot_is_skipped(self):
        task = self.make_task(title="Local title")
        self.run_sync()
        link = NotionTaskLink.objects.get(task=task)

        # Simulate the page coming back in the overlap window, still bot-authored, but with
        # different content than the local task. Echo suppression must leave the task alone.
        self.fake.advance(minutes=5)
        page = self.fake.pages[link.notion_page_id]
        page["properties"][schema.TITLE]["title"][0]["plain_text"] = "Something else"
        self.fake._stamp(page, self.fake.bot_id)

        report = self.run_sync()

        self.assertGreaterEqual(report.skipped_echo, 1)
        task.refresh_from_db()
        self.assertEqual(task.title, "Local title")

    def test_no_ping_pong_after_applying_an_inbound_change(self):
        """The invariant: the engine must never read its own write back as a user edit."""
        self.human_page(title="From Notion")
        self.run_sync()

        # With no user activity on either side, a second and third run must write nothing at all.
        self.fake.calls.clear()
        second = self.run_sync()
        third = self.run_sync()

        for report in (second, third):
            self.assertEqual(report.pushed, 0)
            self.assertEqual(report.created_remotely, 0)
            self.assertEqual(report.created_locally, 0)
            self.assertEqual(report.updated_locally, 0)
        self.assertNotIn("update_page", [name for name, _ in self.fake.calls])


class ConflictTests(SyncTestCase):
    def test_same_minute_conflict_resolves_to_organizer(self):
        task = self.make_task(title="Local")
        self.run_sync()
        link = NotionTaskLink.objects.get(task=task)

        # Backdate both watermarks so each side genuinely counts as changed...
        NotionTaskLink.objects.filter(pk=link.pk).update(
            notion_last_edited_time=timezone.now() - timedelta(minutes=10),
            local_changed_at=timezone.now() - timedelta(minutes=10),
        )
        # ...then let both sides change inside the same minute, which Notion's minute-rounded
        # timestamp cannot order.
        self.fake.edit_as_human(
            link.notion_page_id, {schema.TITLE: {"title": [{"type": "text", "text": {"content": "Notion wins?"}}]}}
        )
        task.title = "Organizer wins"
        task.save()
        self.fake.now = minute_floor(task.changed_date)
        self.fake._stamp(self.fake.pages[link.notion_page_id], HUMAN_ID)

        report = self.run_sync()

        task.refresh_from_db()
        self.assertEqual(task.title, "Organizer wins")
        self.assertEqual(report.conflicts, 1)
        page = self.fake.pages[link.notion_page_id]
        self.assertEqual(page["properties"][schema.TITLE]["title"][0]["plain_text"], "Organizer wins")

    def test_a_clearly_newer_notion_edit_wins(self):
        task = self.make_task(title="Local")
        self.run_sync()
        link = NotionTaskLink.objects.get(task=task)

        task.title = "Local edit"
        task.save()
        # Notion's edit lands a clear five minutes later.
        self.fake.advance(minutes=5)
        self.fake.edit_as_human(
            link.notion_page_id, {schema.TITLE: {"title": [{"type": "text", "text": {"content": "Newer in Notion"}}]}}
        )

        report = self.run_sync()

        task.refresh_from_db()
        self.assertEqual(task.title, "Newer in Notion")
        self.assertEqual(report.conflicts, 1)


class DeletionTests(SyncTestCase):
    def test_a_page_trashed_in_notion_deletes_the_task_on_a_full_sweep(self):
        task = self.make_task()
        self.run_sync()
        link = NotionTaskLink.objects.get(task=task)
        self.fake.trash_as_human(link.notion_page_id)

        report = self.run_sync(full=True)

        self.assertEqual(report.deleted_locally, 1)
        self.assertFalse(TaskItem.objects.filter(pk=task.pk).exists())
        self.assertFalse(NotionTaskLink.objects.filter(pk=link.pk).exists())

    def test_a_page_missing_but_not_trashed_keeps_the_task(self):
        task = self.make_task()
        self.run_sync()
        link = NotionTaskLink.objects.get(task=task)
        # Absent from the query results, but retrieving it shows it is alive.
        self.fake.pages[link.notion_page_id]["in_trash"] = False
        original_query = self.fake.query_data_source
        self.fake.query_data_source = lambda *a, **kw: []

        report = self.run_sync(full=True)
        self.fake.query_data_source = original_query

        self.assertEqual(report.deleted_locally, 0)
        self.assertTrue(TaskItem.objects.filter(pk=task.pk).exists())

    def test_an_unconfirmable_page_never_deletes_the_task(self):
        task = self.make_task()
        self.run_sync()
        link = NotionTaskLink.objects.get(task=task)
        del self.fake.pages[link.notion_page_id]  # retrieve_page will raise

        report = self.run_sync(full=True)

        self.assertEqual(report.deleted_locally, 0)
        self.assertTrue(TaskItem.objects.filter(pk=task.pk).exists())

    def test_incremental_sync_does_not_delete(self):
        task = self.make_task()
        self.run_sync()
        link = NotionTaskLink.objects.get(task=task)
        self.fake.trash_as_human(link.notion_page_id)

        report = self.run_sync(full=False)

        # Only the full sweep can notice a trashed page, so this must be a no-op.
        self.assertEqual(report.deleted_locally, 0)
        self.assertTrue(TaskItem.objects.filter(pk=task.pk).exists())


class BootstrapTests(SyncTestCase):
    def setUp(self):
        super().setUp()
        self.database.bootstrap_state = NotionDatabase.BOOTSTRAP_PENDING
        self.database.save()

    def test_uploads_every_existing_task(self):
        for index in range(5):
            self.make_task(title=f"Task {index}")

        report = self.run_sync()

        self.assertEqual(report.created_remotely, 5)
        self.database.refresh_from_db()
        self.assertEqual(self.database.bootstrap_state, NotionDatabase.BOOTSTRAP_DONE)
        self.assertEqual(NotionTaskLink.objects.count(), 5)

    def test_an_interrupted_bootstrap_resumes_without_duplicates(self):
        tasks = [self.make_task(title=f"Task {index}") for index in range(4)]
        # Simulate a run that died after the first two.
        for task in tasks[:2]:
            page = self.fake.create_page("ds-1", {})
            NotionTaskLink.objects.create(database=self.database, task=task, notion_page_id=page["id"])
        self.database.bootstrap_cursor = tasks[1].pk
        self.database.bootstrap_state = NotionDatabase.BOOTSTRAP_RUNNING
        self.database.save()

        report = self.run_sync()

        self.assertEqual(report.created_remotely, 2)
        self.assertEqual(NotionTaskLink.objects.count(), 4)

    def test_incremental_sync_waits_for_the_bootstrap(self):
        self.human_page(title="Created in Notion first")

        self.run_sync()

        # The bootstrap run must not also pull, or a first-run race could duplicate content.
        self.assertFalse(TaskItem.objects.filter(title="Created in Notion first").exists())

    def test_bootstrap_sets_a_watermark_so_the_first_pull_is_incremental(self):
        self.make_task()

        self.run_sync()

        self.database.refresh_from_db()
        self.assertIsNotNone(self.database.pull_watermark)


class ConnectionStateTests(SyncTestCase):
    def test_schema_drift_pauses_the_sync_without_writing(self):
        self.make_task()
        del self.fake.property_titles[schema.DEADLINE]

        report = self.run_sync()

        self.connection.refresh_from_db()
        self.assertEqual(self.connection.status, self.connection.SCHEMA_DRIFT)
        self.assertEqual(report.created_remotely, 0)
        self.assertEqual(len(self.fake.pages), 0)

    def test_a_successful_sync_records_the_time(self):
        self.make_task()

        self.run_sync()

        self.connection.refresh_from_db()
        self.assertIsNotNone(self.connection.last_synced_at)
        self.assertEqual(self.connection.status, self.connection.ACTIVE)

    def test_a_connection_without_a_database_is_a_no_op(self):
        self.database.delete()
        self.connection.refresh_from_db()
        self.make_task()

        report = sync.sync_connection(self.connection, client=self.fake)

        self.assertEqual(report.created_remotely, 0)


class RichContentTests(SyncTestCase):
    def test_tags_and_project_round_trip(self):
        project = Project.objects.create(title="Home")
        tag = Tag.objects.create(name="errand")
        task = self.make_task(title="Buy milk", project=project)
        task.tags.add(tag)

        self.run_sync()

        page = self.fake.pages[NotionTaskLink.objects.get(task=task).notion_page_id]
        self.assertEqual(page["properties"][schema.PROJECT]["select"]["name"], "Home")
        self.assertEqual([item["name"] for item in page["properties"][schema.TAGS]["multi_select"]], ["errand"])

    def test_an_unknown_project_from_notion_is_ignored(self):
        task = self.make_task(title="t")
        self.run_sync()
        link = NotionTaskLink.objects.get(task=task)

        self.fake.advance(minutes=5)
        self.fake.edit_as_human(link.notion_page_id, {schema.PROJECT: {"select": {"name": "Invented"}}})

        self.run_sync()

        task.refresh_from_db()
        self.assertIsNone(task.project)
        self.assertFalse(Project.objects.filter(title="Invented").exists())

    def test_completion_round_trips(self):
        task = self.make_task(title="t")
        self.run_sync()
        link = NotionTaskLink.objects.get(task=task)

        self.fake.advance(minutes=5)
        self.fake.edit_as_human(link.notion_page_id, {schema.DONE: {"checkbox": True}})

        self.run_sync()

        task.refresh_from_db()
        self.assertTrue(task.completed)


class SyncAllTests(SyncTestCase):
    def test_one_failing_connection_does_not_abort_the_batch(self):
        from integrations.notion.tasks import sync_all

        other_user = make_user("second")
        other_connection = make_connection(other_user)
        make_database(other_connection)
        self.make_task()
        TaskItem.objects.create(owner=other_user, title="Theirs")

        calls = {"count": 0}

        def flaky(connection, full=False):
            calls["count"] += 1
            if calls["count"] == 1:
                raise RuntimeError("boom")
            return sync.SyncReport()

        import integrations.notion.sync as sync_module

        original = sync_module.sync_connection
        sync_module.sync_connection = flaky
        try:
            processed = sync_all()
        finally:
            sync_module.sync_connection = original

        # Two connections attempted, one blew up, the other still ran.
        self.assertEqual(calls["count"], 2)
        self.assertEqual(processed, 1)

    def test_connections_needing_reauth_are_skipped(self):
        from integrations.notion.tasks import sync_all

        self.connection.status = self.connection.NEEDS_REAUTH
        self.connection.save()
        self.make_task()

        self.assertEqual(sync_all(), 0)


class WatermarkTests(SyncTestCase):
    def test_watermarks_are_stamped_after_a_push(self):
        task = self.make_task()

        self.run_sync()

        link = NotionTaskLink.objects.get(task=task)
        self.assertIsNotNone(link.notion_last_edited_time)
        self.assertIsNotNone(link.local_changed_at)
        # The local watermark must match the task's own changed_date exactly, or the next run
        # would see a phantom local edit.
        task.refresh_from_db()
        self.assertEqual(link.local_changed_at, task.changed_date)

    def test_watermarks_are_stamped_after_an_inbound_apply(self):
        self.human_page(title="Inbound")

        self.run_sync()

        task = TaskItem.objects.get(title="Inbound")
        link = NotionTaskLink.objects.get(task=task)
        self.assertEqual(link.local_changed_at, task.changed_date)
        self.assertIsNotNone(link.notion_last_edited_time)

    def test_a_full_sync_records_its_timestamp(self):
        self.run_sync(full=True)

        self.connection.refresh_from_db()
        self.assertIsNotNone(self.connection.last_full_sync_at)

    def test_full_sync_becomes_due_after_the_configured_interval(self):
        self.connection.last_full_sync_at = timezone.now() - timedelta(hours=48)
        self.connection.save()

        self.assertTrue(sync._is_full_sync_due(self.connection))

        self.connection.last_full_sync_at = timezone.now()
        self.assertFalse(sync._is_full_sync_due(self.connection))


class RelationEfficiencyTests(SyncTestCase):
    def test_parent_relations_are_not_rewritten_on_every_sync(self):
        parent = self.make_task(title="Parent")
        self.make_task(title="Child", parent_task=parent)
        self.run_sync()

        # A steady-state run must not touch Notion at all. Re-patching the relation every time
        # would burn the rate limit and churn last_edited_time for no reason.
        self.fake.calls.clear()
        self.run_sync()

        self.assertNotIn("update_page", [name for name, _ in self.fake.calls])
