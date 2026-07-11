from django.contrib.auth import get_user_model
from rest_framework.test import APITestCase

from tasks.models import TaskComment, TaskItem

User = get_user_model()


class TaskCommentAPITests(APITestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="owner", password="pw")
        self.other = User.objects.create_user(username="other", password="pw")
        self.task = TaskItem.objects.create(title="mine", owner=self.user)
        self.other_task = TaskItem.objects.create(title="theirs", owner=self.other)
        self.client.force_authenticate(self.user)

    def test_create_sets_author_and_associates_task(self):
        response = self.client.post(
            "/api/comments/", {"task": self.task.pk, "description": "first note"}, format="json"
        )
        self.assertEqual(response.status_code, 201, response.data)
        comment = TaskComment.objects.get(pk=response.data["id"])
        self.assertEqual(comment.user, self.user)
        self.assertEqual(comment.task, self.task)
        self.assertEqual(response.data["user_username"], "owner")

    def test_author_is_not_client_controlled(self):
        # A client trying to attribute the comment to someone else is ignored.
        response = self.client.post(
            "/api/comments/",
            {"task": self.task.pk, "description": "sneaky", "user": self.other.pk},
            format="json",
        )
        self.assertEqual(response.status_code, 201, response.data)
        self.assertEqual(TaskComment.objects.get(pk=response.data["id"]).user, self.user)

    def test_cannot_comment_on_other_users_task(self):
        response = self.client.post(
            "/api/comments/", {"task": self.other_task.pk, "description": "nope"}, format="json"
        )
        self.assertEqual(response.status_code, 403)
        self.assertFalse(TaskComment.objects.filter(task=self.other_task).exists())

    def test_list_is_owner_scoped(self):
        TaskComment.objects.create(task=self.task, user=self.user, description="mine")
        TaskComment.objects.create(task=self.other_task, user=self.other, description="theirs")
        response = self.client.get("/api/comments/")
        self.assertEqual(response.status_code, 200)
        descriptions = {c["description"] for c in response.data}
        self.assertEqual(descriptions, {"mine"})

    def test_unauthenticated_is_rejected(self):
        self.client.force_authenticate(None)
        response = self.client.get("/api/comments/")
        self.assertIn(response.status_code, (401, 403))


class TaskSerializerReadFieldsTests(APITestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="owner", password="pw")
        self.client.force_authenticate(self.user)

    def test_detail_exposes_metadata_parent_and_comments(self):
        parent = TaskItem.objects.create(title="parent", owner=self.user)
        task = TaskItem.objects.create(title="child", owner=self.user, parent_task=parent)
        TaskComment.objects.create(task=task, user=self.user, description="a note")

        response = self.client.get(f"/api/task/{task.pk}/")
        self.assertEqual(response.status_code, 200, response.data)
        self.assertIn("created_date", response.data)
        self.assertIsNotNone(response.data["created_date"])
        self.assertEqual(response.data["parent_task"], parent.pk)
        self.assertEqual(response.data["parent_task_title"], "parent")
        self.assertEqual(len(response.data["comments"]), 1)
        self.assertEqual(response.data["comments"][0]["description"], "a note")
        # No recurring template attached → template context is null, not absent.
        self.assertIsNone(response.data["template"])
        self.assertIsNone(response.data["template_title"])
