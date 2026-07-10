"""Unit tests for the MCP service layer (mcp_server/service.py).

Runs synchronously against the ORM/serializers, exercising CRUD, owner scoping, filtering,
and comment authorship without the async transport or OAuth stack.
"""

from django.contrib.auth import get_user_model
from django.test import TestCase

from mcp_server import service
from tasks.models import TaskComment, TaskItem

User = get_user_model()


class TaskServiceTests(TestCase):
    def setUp(self):
        self.owner = User.objects.create_user("owner", password="pw")
        self.other = User.objects.create_user("other", password="pw")

    def test_create_is_owned_by_user(self):
        task = service.create_task(self.owner.id, title="Write report")
        self.assertEqual(task["title"], "Write report")
        self.assertEqual(task["owner"], self.owner.id)
        self.assertEqual(task["status"], TaskItem.IDEA)
        self.assertEqual(task["priority"], TaskItem.NORMAL)

    def test_list_is_scoped_to_owner(self):
        service.create_task(self.owner.id, title="Mine")
        service.create_task(self.other.id, title="Theirs")

        mine = service.list_tasks(self.owner.id)
        self.assertEqual(mine["count"], 1)
        self.assertEqual(mine["results"][0]["title"], "Mine")

        theirs = service.list_tasks(self.other.id)
        self.assertEqual(theirs["count"], 1)
        self.assertEqual(theirs["results"][0]["title"], "Theirs")

    def test_get_other_users_task_is_not_found(self):
        task = service.create_task(self.owner.id, title="Secret")
        with self.assertRaises(service.NotFound):
            service.get_task(self.other.id, task["id"])

    def test_update_and_completion_timestamp(self):
        task = service.create_task(self.owner.id, title="Do")
        self.assertIsNone(task["completed_date"])

        completed = service.update_task(self.owner.id, task["id"], completed=True)
        self.assertTrue(completed["completed"])
        self.assertIsNotNone(completed["completed_date"])

        reopened = service.update_task(self.owner.id, task["id"], completed=False)
        self.assertFalse(reopened["completed"])
        self.assertIsNone(reopened["completed_date"])

    def test_delete_task(self):
        task = service.create_task(self.owner.id, title="Temp")
        service.delete_task(self.owner.id, task["id"])
        self.assertFalse(TaskItem.objects.filter(pk=task["id"]).exists())

    def test_cannot_delete_other_users_task(self):
        task = service.create_task(self.owner.id, title="Keep")
        with self.assertRaises(service.NotFound):
            service.delete_task(self.other.id, task["id"])
        self.assertTrue(TaskItem.objects.filter(pk=task["id"]).exists())

    def test_create_requires_title(self):
        with self.assertRaises(ValueError):
            service.create_task(self.owner.id, description="no title")

    def test_filter_by_search_status_priority(self):
        service.create_task(self.owner.id, title="Buy milk", status=TaskItem.IN_PROGRESS, priority=TaskItem.HIGH)
        service.create_task(self.owner.id, title="Buy bread", status=TaskItem.IDEA, priority=TaskItem.LOW)

        self.assertEqual(service.list_tasks(self.owner.id, search="milk")["count"], 1)
        self.assertEqual(service.list_tasks(self.owner.id, status=TaskItem.IN_PROGRESS)["count"], 1)
        self.assertEqual(service.list_tasks(self.owner.id, priority=TaskItem.HIGH)["count"], 1)
        self.assertEqual(service.list_tasks(self.owner.id, search="Buy")["count"], 2)

    def test_filter_for_today(self):
        service.create_task(self.owner.id, title="Today", for_today=True)
        service.create_task(self.owner.id, title="Someday", for_today=False)
        result = service.list_tasks(self.owner.id, for_today=True)
        self.assertEqual(result["count"], 1)
        self.assertEqual(result["results"][0]["title"], "Today")

    def test_pagination_window(self):
        for i in range(5):
            service.create_task(self.owner.id, title=f"T{i}", order=i)
        page = service.list_tasks(self.owner.id, limit=2, offset=0)
        self.assertEqual(page["count"], 5)
        self.assertEqual(len(page["results"]), 2)


class TagProjectServiceTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user("u", password="pw")

    def test_tag_crud_and_task_association(self):
        tag = service.create_tag(name="Urgent", color="#FF0000")
        self.assertEqual(tag["slug"], "urgent")

        listed = service.list_tags()
        self.assertEqual(listed["count"], 1)

        updated = service.update_tag(tag["id"], description="high priority")
        self.assertEqual(updated["description"], "high priority")

        task = service.create_task(self.user.id, title="Tagged", tags=[tag["id"]])
        self.assertEqual(task["tags"], [tag["id"]])

        # A tag with an associated task reports a count.
        self.assertEqual(service.get_tag(tag["id"])["count"], 1)

    def test_tag_delete(self):
        tag = service.create_tag(name="Temp")
        service.delete_tag(tag["id"])
        with self.assertRaises(service.NotFound):
            service.get_tag(tag["id"])

    def test_project_crud(self):
        project = service.create_project(title="Website")
        self.assertEqual(project["slug"], "website")

        self.assertEqual(service.list_projects()["count"], 1)

        updated = service.update_project(project["id"], description="marketing site")
        self.assertEqual(updated["description"], "marketing site")

        service.delete_project(project["id"])
        with self.assertRaises(service.NotFound):
            service.get_project(project["id"])


class CommentServiceTests(TestCase):
    def setUp(self):
        self.owner = User.objects.create_user("owner", password="pw")
        self.other = User.objects.create_user("other", password="pw")
        self.task = service.create_task(self.owner.id, title="Discuss")

    def test_add_records_author_and_lists(self):
        comment = service.add_task_comment(self.owner.id, self.task["id"], "First note")
        self.assertEqual(comment["user"], self.owner.id)
        self.assertEqual(comment["description"], "First note")

        comments = service.list_task_comments(self.owner.id, self.task["id"])
        self.assertEqual(comments["count"], 1)
        self.assertEqual(comments["results"][0]["description"], "First note")

    def test_cannot_comment_on_other_users_task(self):
        with self.assertRaises(service.NotFound):
            service.add_task_comment(self.other.id, self.task["id"], "intruder")

    def test_delete_comment(self):
        comment = service.add_task_comment(self.owner.id, self.task["id"], "temp")
        service.delete_task_comment(self.owner.id, comment["id"])
        self.assertFalse(TaskComment.objects.filter(pk=comment["id"]).exists())
