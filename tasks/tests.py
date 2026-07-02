from django.contrib.auth import get_user_model
from django.utils import timezone
from rest_framework.test import APITestCase

from tasks.models import TaskComment, TaskItem

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
        response = self.client.post(
            "/api/task/", {"title": "new", "owner": self.other.pk}, format="json"
        )

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
