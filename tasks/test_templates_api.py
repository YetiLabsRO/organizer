from datetime import date

from django.contrib.auth import get_user_model
from django.core.management import call_command
from rest_framework.test import APITestCase

from tasks.models import TaskItem, TaskTemplate

User = get_user_model()


class TaskTemplateAPITests(APITestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="owner", password="pw")
        self.other = User.objects.create_user(username="other", password="pw")
        self.client.force_authenticate(self.user)

    def _payload(self, **overrides):
        payload = {
            "title": "Monthly financial documents",
            "frequency": TaskTemplate.MONTHLY,
            "interval": 1,
            "day_of_month": 1,
            "start_on": "2026-01-15",
        }
        payload.update(overrides)
        return payload

    def test_create_sets_owner_and_reports_schedule(self):
        response = self.client.post("/api/template/", self._payload(), format="json")
        self.assertEqual(response.status_code, 201, response.data)
        self.assertEqual(response.data["schedule_summary"], "Every month on day 1")
        # next_occurrence is relative to the real current date; for a "1st of month" rule it always
        # lands on the 1st (clock-independent assertion).
        self.assertTrue(response.data["next_occurrence"].endswith("-01"))
        template = TaskTemplate.objects.get(pk=response.data["id"])
        self.assertEqual(template.owner, self.user)

    def test_list_is_owner_scoped(self):
        TaskTemplate.objects.create(title="mine", owner=self.user)
        TaskTemplate.objects.create(title="theirs", owner=self.other)
        response = self.client.get("/api/template/")
        self.assertEqual(response.status_code, 200)
        titles = {t["title"] for t in response.data}
        self.assertEqual(titles, {"mine"})

    def test_cannot_retrieve_other_users_template(self):
        theirs = TaskTemplate.objects.create(title="theirs", owner=self.other)
        response = self.client.get(f"/api/template/{theirs.pk}/")
        self.assertEqual(response.status_code, 404)

    def test_validation_rejects_bad_interval(self):
        response = self.client.post("/api/template/", self._payload(interval=0), format="json")
        self.assertEqual(response.status_code, 400)
        self.assertIn("interval", response.data)

    def test_validation_rejects_end_before_start(self):
        response = self.client.post(
            "/api/template/", self._payload(start_on="2026-02-01", end_on="2026-01-01"), format="json"
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn("end_on", response.data)

    def test_run_action_generates_due_task(self):
        template = TaskTemplate.objects.create(
            title="daily thing", owner=self.user, frequency=TaskTemplate.DAILY, start_on=date(2020, 1, 1)
        )
        response = self.client.post(f"/api/template/{template.pk}/run/")
        self.assertEqual(response.status_code, 201, response.data)
        self.assertEqual(response.data["template"], template.pk)
        self.assertEqual(TaskItem.objects.filter(template=template).count(), 1)

    def test_run_action_reports_nothing_due(self):
        # Starts in the future → nothing to generate yet.
        template = TaskTemplate.objects.create(
            title="future", owner=self.user, frequency=TaskTemplate.DAILY, start_on=date(2099, 1, 1)
        )
        response = self.client.post(f"/api/template/{template.pk}/run/")
        self.assertEqual(response.status_code, 200)
        self.assertIn("detail", response.data)

    def test_task_serializer_exposes_template_link(self):
        template = TaskTemplate.objects.create(
            title="daily", owner=self.user, frequency=TaskTemplate.DAILY, start_on=date(2020, 1, 1)
        )
        self.client.post(f"/api/template/{template.pk}/run/")
        generated = TaskItem.objects.get(template=template)

        detail = self.client.get(f"/api/task/{generated.pk}/")
        self.assertEqual(detail.data["template"], template.pk)

        manual = TaskItem.objects.create(title="manual", owner=self.user)
        manual_detail = self.client.get(f"/api/task/{manual.pk}/")
        self.assertIsNone(manual_detail.data["template"])


class GenerateCommandTests(APITestCase):
    def test_command_generates_for_active_templates(self):
        user = User.objects.create_user(username="owner", password="pw")
        TaskTemplate.objects.create(title="daily", owner=user, frequency=TaskTemplate.DAILY, start_on=date(2026, 1, 1))
        call_command("generate_recurring_tasks", "--date", "2026-01-10")
        self.assertEqual(TaskItem.objects.count(), 1)
        # Idempotent on re-run for the same date.
        call_command("generate_recurring_tasks", "--date", "2026-01-10")
        self.assertEqual(TaskItem.objects.count(), 1)
