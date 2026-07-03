from datetime import datetime, timedelta
from io import StringIO

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APITestCase

from tasks.models import Tag, TaskComment, TaskItem

User = get_user_model()


class TaskListPaginationTests(APITestCase):
    """Covers the windowed-list contract: pagination envelope, owner scoping, light payload."""

    def setUp(self):
        self.user = User.objects.create_user(username="owner", password="pw")
        self.other = User.objects.create_user(username="other", password="pw")
        self.client.force_authenticate(self.user)

    def test_list_returns_pagination_envelope(self):
        for i in range(3):
            TaskItem.objects.create(title=f"t{i}", owner=self.user)

        response = self.client.get("/api/task/")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(set(response.data), {"count", "next", "previous", "results"})
        self.assertEqual(response.data["count"], 3)
        self.assertEqual(len(response.data["results"]), 3)

    def test_limit_and_offset_window(self):
        for i in range(5):
            TaskItem.objects.create(title=f"t{i}", order=i, owner=self.user)

        response = self.client.get("/api/task/?limit=2&offset=2")

        self.assertEqual(response.data["count"], 5)
        self.assertEqual(len(response.data["results"]), 2)

    def test_list_is_scoped_to_owner(self):
        TaskItem.objects.create(title="mine", owner=self.user)
        TaskItem.objects.create(title="theirs", owner=self.other)

        response = self.client.get("/api/task/")

        titles = [t["title"] for t in response.data["results"]]
        self.assertEqual(response.data["count"], 1)
        self.assertEqual(titles, ["mine"])

    def test_create_sets_owner_to_request_user(self):
        response = self.client.post("/api/task/", {"title": "new", "owner": self.other.pk}, format="json")

        self.assertEqual(response.status_code, 201)
        self.assertEqual(TaskItem.objects.get(title="new").owner, self.user)

    def test_list_omits_comments_but_detail_includes_them(self):
        task = TaskItem.objects.create(title="withcomment", owner=self.user)
        TaskComment.objects.create(task=task, user=self.user, description="hi")

        list_item = self.client.get("/api/task/").data["results"][0]
        detail = self.client.get(f"/api/task/{task.pk}/").data

        self.assertNotIn("comments", list_item)
        self.assertIn("comments", detail)
        self.assertEqual(len(detail["comments"]), 1)

    def test_today_view_combines_focus_and_completed_today(self):
        focus = TaskItem.objects.create(title="focus", for_today=True, owner=self.user)
        done_today = TaskItem.objects.create(title="done", completed=True, owner=self.user)
        done_today.completed_date = timezone.now()
        done_today.save()
        TaskItem.objects.create(title="neither", owner=self.user)

        response = self.client.get("/api/task/?today_view=true")

        titles = {t["title"] for t in response.data["results"]}
        self.assertEqual(titles, {"focus", "done"})
        self.assertIn(focus.pk, {t["id"] for t in response.data["results"]})

    def test_multiple_tags_filter_is_conjoined_and(self):
        from tasks.models import Tag

        work = Tag.objects.create(name="work", slug="work")
        urgent = Tag.objects.create(name="urgent", slug="urgent")
        both = TaskItem.objects.create(title="both", owner=self.user)
        both.tags.set([work, urgent])
        only_work = TaskItem.objects.create(title="onlywork", owner=self.user)
        only_work.tags.set([work])

        response = self.client.get("/api/task/?tags=work&tags=urgent")

        titles = [t["title"] for t in response.data["results"]]
        self.assertEqual(titles, ["both"])


class TaskStatsTests(APITestCase):
    """Covers the `/api/task/stats/` aggregation: auth, scoping, filters, bucketing, semantics."""

    URL = "/api/task/stats/"

    def setUp(self):
        self.user = User.objects.create_user(username="owner", password="pw")
        self.other = User.objects.create_user(username="other", password="pw")
        self.client.force_authenticate(self.user)
        self.work = Tag.objects.create(name="work", slug="work")
        self.urgent = Tag.objects.create(name="urgent", slug="urgent")
        # Fixed dates: Mon/Tue/Wed of the same ISO week, plus the following week.
        self.mon = timezone.make_aware(datetime(2026, 1, 5, 12, 0))
        self.tue = timezone.make_aware(datetime(2026, 1, 6, 12, 0))
        self.wed = timezone.make_aware(datetime(2026, 1, 7, 12, 0))
        self.next_week = timezone.make_aware(datetime(2026, 1, 14, 12, 0))

    def _solved(self, title, completed_when, *, tags=None, created=None, owner=None):
        task = TaskItem.objects.create(title=title, owner=owner or self.user, completed=True)
        if tags:
            task.tags.set(tags)
        TaskItem.objects.filter(pk=task.pk).update(
            completed_date=completed_when, created_date=created or completed_when
        )
        return task

    def test_requires_authentication(self):
        self.client.force_authenticate(None)
        response = self.client.get(self.URL)
        self.assertIn(response.status_code, (401, 403))

    def test_invalid_bucket_rejected(self):
        response = self.client.get(self.URL, {"bucket": "fortnight"})
        self.assertEqual(response.status_code, 400)

    def test_scoped_to_owner(self):
        self._solved("mine", self.mon)
        self._solved("theirs", self.mon, owner=self.other)

        data = self.client.get(self.URL).data

        self.assertEqual(data["totals"]["total"], 1)
        self.assertEqual(data["totals"]["completed"], 1)

    def test_filters_are_honoured(self):
        self._solved("w", self.mon, tags=[self.work])
        self._solved("u", self.mon, tags=[self.urgent])

        data = self.client.get(self.URL, {"tags": "work"}).data

        self.assertEqual(data["totals"]["total"], 1)
        self.assertEqual({row["slug"] for row in data["tag_distribution"]}, {"work"})

    def test_tag_distribution_counts_per_tag_and_untagged(self):
        self._solved("both", self.mon, tags=[self.work, self.urgent])
        TaskItem.objects.create(title="untagged", owner=self.user)

        rows = {row["slug"]: row["count"] for row in self.client.get(self.URL).data["tag_distribution"]}

        self.assertEqual(rows["work"], 1)
        self.assertEqual(rows["urgent"], 1)
        self.assertEqual(rows[None], 1)  # untagged bucket

    def test_solved_timeline_day_vs_week(self):
        self._solved("a", self.mon)
        self._solved("b", self.tue)
        self._solved("c", self.wed)

        by_day = self.client.get(self.URL, {"bucket": "day"}).data["solved_timeline"]
        by_week = self.client.get(self.URL, {"bucket": "week"}).data["solved_timeline"]

        self.assertEqual(len(by_day), 3)  # three distinct days
        self.assertEqual(len(by_week), 1)  # all in the same ISO week
        self.assertEqual(by_week[0]["count"], 3)

    def test_timeline_excludes_non_completed(self):
        self._solved("done", self.mon)
        TaskItem.objects.create(title="open", owner=self.user, completed=False)

        data = self.client.get(self.URL).data

        self.assertEqual(sum(row["count"] for row in data["solved_timeline"]), 1)
        self.assertEqual(sum(row["count"] for row in data["calendar_heatmap"]), 1)
        self.assertEqual(data["totals"]["total"], 2)  # distribution/totals still see the open task

    def test_solved_by_tag_timeline_multi_tag(self):
        self._solved("both", self.mon, tags=[self.work, self.urgent])

        payload = self.client.get(self.URL, {"bucket": "week"}).data["solved_by_tag_timeline"]

        self.assertEqual(payload["periods"], ["2026-01-05"])
        totals = {s["slug"]: sum(s["counts"]) for s in payload["series"]}
        self.assertEqual(totals["work"], 1)
        self.assertEqual(totals["urgent"], 1)

    def test_created_vs_completed_timeline(self):
        # Created one week, completed the next.
        self._solved("t", self.next_week, created=self.mon)

        data = self.client.get(self.URL, {"bucket": "week"}).data
        rows = {r["period"]: r for r in data["created_vs_completed_timeline"]}

        self.assertEqual(rows["2026-01-05"]["created"], 1)
        self.assertEqual(rows["2026-01-12"]["completed"], 1)

    def test_time_to_completion_by_tag(self):
        self._solved("t", self.mon + timedelta(days=4), tags=[self.work], created=self.mon)

        rows = {r["slug"]: r for r in self.client.get(self.URL).data["time_to_completion_by_tag"]}

        self.assertEqual(rows["work"]["count"], 1)
        self.assertAlmostEqual(rows["work"]["avg_days"], 4.0, places=2)


class BackfillTaskOwnerCommandTests(TestCase):
    """The ownership backfill used to un-hide legacy tasks after owner scoping."""

    def test_dry_run_changes_nothing(self):
        User.objects.create_user(username="target")
        task = TaskItem.objects.create(title="orphan")

        call_command("backfill_task_owner", "--username", "target", stdout=StringIO())

        task.refresh_from_db()
        self.assertIsNone(task.owner)

    def test_only_unowned_leaves_other_owners_untouched(self):
        target = User.objects.create_user(username="target")
        other = User.objects.create_user(username="other")
        orphan = TaskItem.objects.create(title="orphan")
        owned = TaskItem.objects.create(title="owned", owner=other)

        call_command(
            "backfill_task_owner",
            "--username",
            "target",
            "--only-unowned",
            "--apply",
            stdout=StringIO(),
        )

        orphan.refresh_from_db()
        owned.refresh_from_db()
        self.assertEqual(orphan.owner, target)
        self.assertEqual(owned.owner, other)

    def test_apply_claims_all_tasks(self):
        target = User.objects.create_user(username="target", email="me@example.com")
        other = User.objects.create_user(username="other")
        TaskItem.objects.create(title="orphan")
        TaskItem.objects.create(title="owned", owner=other)

        call_command("backfill_task_owner", "--email", "me@example.com", "--apply", stdout=StringIO())

        self.assertEqual(TaskItem.objects.filter(owner=target).count(), 2)
