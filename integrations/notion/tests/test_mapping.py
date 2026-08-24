"""Field mapping — chiefly the places where a naive copy would lose data."""

from datetime import datetime, timedelta

from django.test import TestCase
from django.utils import timezone

from integrations.notion import mapping, schema
from integrations.notion.tests.fakes import _read_shape
from integrations.notion.tests.helpers import ALL_PROPERTIES, make_user
from tasks.models import Project, Tag, TaskItem

NAMES = {name: name for name in ALL_PROPERTIES}


def page_with(**properties):
    return {"id": "page-1", "properties": _read_shape(properties)}


class OutboundTests(TestCase):
    def setUp(self):
        self.user = make_user()

    def test_every_owned_field_is_written(self):
        project = Project.objects.create(title="Home")
        tag = Tag.objects.create(name="errand", color="#448383")
        task = TaskItem.objects.create(
            owner=self.user,
            title="Buy milk",
            description="Semi-skimmed",
            status=TaskItem.IN_PROGRESS,
            priority=TaskItem.HIGH,
            estimated_time=15,
            for_today=True,
            project=project,
        )
        task.tags.add(tag)

        properties = mapping.task_to_properties(task, NAMES)

        self.assertEqual(properties[schema.TITLE]["title"][0]["text"]["content"], "Buy milk")
        self.assertEqual(properties[schema.DESCRIPTION]["rich_text"][0]["text"]["content"], "Semi-skimmed")
        self.assertEqual(properties[schema.STATUS]["select"]["name"], "În lucru")
        self.assertEqual(properties[schema.PRIORITY]["select"]["name"], "Prioritară")
        self.assertEqual(properties[schema.ESTIMATE]["number"], 15)
        self.assertTrue(properties[schema.TODAY]["checkbox"])
        self.assertEqual(properties[schema.PROJECT]["select"]["name"], "Home")
        self.assertEqual([item["name"] for item in properties[schema.TAGS]["multi_select"]], ["errand"])

    def test_long_description_is_chunked_not_truncated(self):
        task = TaskItem.objects.create(owner=self.user, title="t", description="x" * 5000)
        chunks = mapping.task_to_properties(task, NAMES)[schema.DESCRIPTION]["rich_text"]

        self.assertEqual(len(chunks), 3)
        self.assertTrue(all(len(chunk["text"]["content"]) <= 2000 for chunk in chunks))
        self.assertEqual("".join(chunk["text"]["content"] for chunk in chunks), "x" * 5000)

    def test_cleared_parent_sends_an_empty_relation(self):
        task = TaskItem.objects.create(owner=self.user, title="t")
        properties = mapping.task_to_properties(task, NAMES, parent_page_id=None)
        self.assertEqual(properties[schema.PARENT_TASK]["relation"], [])


class InboundDateTests(TestCase):
    """Notion hands back midnight for a date picked without a time."""

    def setUp(self):
        self.user = make_user()

    def test_date_only_value_preserves_the_local_time_of_day(self):
        deadline = timezone.make_aware(datetime(2026, 7, 15, 14, 30), timezone.get_current_timezone())
        page = page_with(**{schema.DEADLINE: {"date": {"start": "2026-07-15"}}})

        result = mapping.read_datetime(page, NAMES, schema.DEADLINE, deadline)

        # The 14:30 must survive: Notion simply cannot show it.
        self.assertEqual(result, deadline)

    def test_a_genuinely_moved_date_is_applied(self):
        deadline = timezone.make_aware(datetime(2026, 7, 15, 14, 30), timezone.get_current_timezone())
        page = page_with(**{schema.DEADLINE: {"date": {"start": "2026-07-20"}}})

        result = mapping.read_datetime(page, NAMES, schema.DEADLINE, deadline)

        self.assertEqual(timezone.localtime(result).date(), datetime(2026, 7, 20).date())

    def test_a_datetime_from_notion_is_applied_in_full(self):
        page = page_with(**{schema.DEADLINE: {"date": {"start": "2026-07-20T09:15:00.000Z"}}})
        result = mapping.read_datetime(page, NAMES, schema.DEADLINE, None)
        self.assertEqual(result.hour, 9)
        self.assertEqual(result.minute, 15)

    def test_cleared_date_reads_as_none(self):
        page = page_with(**{schema.DEADLINE: {"date": None}})
        self.assertIsNone(mapping.read_datetime(page, NAMES, schema.DEADLINE, timezone.now()))


class CompletedDateTests(TestCase):
    """``completed_date`` is a MonitorField and fights back."""

    def test_notions_completion_timestamp_survives_monitorfield(self):
        user = make_user()
        task = TaskItem.objects.create(owner=user, title="t")
        yesterday = timezone.now() - timedelta(days=1)

        task.completed = True
        task.save()
        # MonitorField has now stamped completed_date as "just now".
        self.assertGreater(task.completed_date, yesterday + timedelta(hours=1))

        mapping.apply_completed_date(task, yesterday)

        task.refresh_from_db()
        self.assertAlmostEqual(task.completed_date, yesterday, delta=timedelta(seconds=1))

    def test_correcting_completed_date_does_not_look_like_a_local_edit(self):
        # It goes through queryset.update(), which also bypasses auto_now on changed_date —
        # otherwise the next sync would push this correction back as a user edit.
        user = make_user()
        task = TaskItem.objects.create(owner=user, title="t", completed=True)
        before = TaskItem.objects.get(pk=task.pk).changed_date

        mapping.apply_completed_date(task, timezone.now() - timedelta(days=3))

        self.assertEqual(TaskItem.objects.get(pk=task.pk).changed_date, before)


class GlobalRecordTests(TestCase):
    """Projects and tags have no owner, so Notion values are matched, never created."""

    def setUp(self):
        self.user = make_user()
        self.project = Project.objects.create(title="Home")
        self.tag = Tag.objects.create(name="errand")

    def test_known_project_is_matched_case_insensitively(self):
        self.assertEqual(mapping.resolve_project("home", None), self.project)

    def test_unknown_project_is_ignored_and_nothing_is_created(self):
        current = self.project
        result = mapping.resolve_project("Totally New Project", current)

        self.assertEqual(result, current)
        self.assertEqual(Project.objects.count(), 1)

    def test_unknown_tags_are_ignored(self):
        resolved, unresolved = mapping.resolve_tags(["errand", "invented"])

        self.assertEqual(resolved, [self.tag])
        self.assertEqual(unresolved, ["invented"])
        self.assertEqual(Tag.objects.count(), 1)

    def test_an_entirely_unknown_tag_set_leaves_existing_tags_alone(self):
        task = TaskItem.objects.create(owner=self.user, title="t")
        task.tags.add(self.tag)

        changed = mapping.sync_tags(task, ["invented", "also-invented"])

        self.assertFalse(changed)
        self.assertEqual(list(task.tags.all()), [self.tag])

    def test_clearing_tags_in_notion_clears_them_locally(self):
        task = TaskItem.objects.create(owner=self.user, title="t")
        task.tags.add(self.tag)

        self.assertTrue(mapping.sync_tags(task, []))
        self.assertEqual(list(task.tags.all()), [])


class InboundApplyTests(TestCase):
    def setUp(self):
        self.user = make_user()

    def test_reapplying_the_same_page_reports_no_change(self):
        task = TaskItem.objects.create(owner=self.user, title="Buy milk", status=TaskItem.IDEA)
        page = page_with(
            **{
                schema.TITLE: {"title": [{"type": "text", "text": {"content": "Buy milk"}}]},
                schema.STATUS: {"select": {"name": "Idee"}},
                schema.DONE: {"checkbox": False},
            }
        )

        mapping.apply_page_to_task(page, task, NAMES)
        task.save()
        changed, _ = mapping.apply_page_to_task(page, task, NAMES)

        # Idempotence is what keeps the overlapping pull window from writing on every run.
        self.assertFalse(changed)

    def test_unknown_status_option_leaves_the_local_status(self):
        task = TaskItem.objects.create(owner=self.user, title="t", status=TaskItem.BLOCKED)
        page = page_with(**{schema.STATUS: {"select": {"name": "Whatever"}}})

        mapping.apply_page_to_task(page, task, NAMES)

        self.assertEqual(task.status, TaskItem.BLOCKED)
