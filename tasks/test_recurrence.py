from datetime import date, timedelta

from django.contrib.auth import get_user_model
from django.test import TestCase

from tasks import recurrence
from tasks.models import TaskItem, TaskTemplate

User = get_user_model()


def _first_monday_on_or_after(d: date) -> date:
    return d + timedelta(days=(7 - d.weekday()) % 7)


class OccurrenceMathTests(TestCase):
    """Pure occurrence math — no DB writes needed, but TaskTemplate needs a user/owner."""

    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(username="owner", password="pw")

    def _template(self, **kwargs):
        kwargs.setdefault("title", "T")
        kwargs.setdefault("owner", self.user)
        return TaskTemplate.objects.create(**kwargs)

    # --- daily ---
    def test_daily_basic(self):
        t = self._template(frequency=TaskTemplate.DAILY, start_on=date(2026, 1, 1))
        self.assertEqual(recurrence.first_occurrence(t), date(2026, 1, 1))
        self.assertEqual(recurrence.step(t, date(2026, 1, 1)), date(2026, 1, 2))
        self.assertEqual(recurrence.latest_occurrence_on_or_before(t, date(2026, 1, 11)), date(2026, 1, 11))

    def test_daily_interval(self):
        t = self._template(frequency=TaskTemplate.DAILY, interval=3, start_on=date(2026, 1, 1))
        # Jan 1, 4, 7, 10 ... latest on/before Jan 11 is Jan 10.
        self.assertEqual(recurrence.latest_occurrence_on_or_before(t, date(2026, 1, 11)), date(2026, 1, 10))
        self.assertEqual(recurrence.occurrence_on_or_after(t, date(2026, 1, 2)), date(2026, 1, 4))

    # --- weekly ---
    def test_weekly_every_two_weeks(self):
        monday = _first_monday_on_or_after(date(2026, 1, 1))
        t = self._template(frequency=TaskTemplate.WEEKLY, interval=2, weekdays=[0], start_on=monday)
        self.assertEqual(recurrence.first_occurrence(t), monday)
        self.assertEqual(recurrence.step(t, monday), monday + timedelta(days=14))
        self.assertEqual(
            recurrence.latest_occurrence_on_or_before(t, monday + timedelta(days=20)),
            monday + timedelta(days=14),
        )

    def test_weekly_multiple_weekdays(self):
        monday = _first_monday_on_or_after(date(2026, 1, 1))
        t = self._template(frequency=TaskTemplate.WEEKLY, weekdays=[0, 2], start_on=monday)  # Mon + Wed
        self.assertEqual(recurrence.step(t, monday), monday + timedelta(days=2))  # Wed
        self.assertEqual(recurrence.step(t, monday + timedelta(days=2)), monday + timedelta(days=7))  # next Mon

    # --- monthly ---
    def test_monthly_first_occurrence_after_anchor(self):
        # day_of_month (1) is before the anchor day (10) → first occurrence is next month's 1st.
        t = self._template(frequency=TaskTemplate.MONTHLY, day_of_month=1, start_on=date(2026, 1, 10))
        self.assertEqual(recurrence.first_occurrence(t), date(2026, 2, 1))
        self.assertEqual(recurrence.step(t, date(2026, 2, 1)), date(2026, 3, 1))

    def test_monthly_day_clamps_to_short_month(self):
        t = self._template(frequency=TaskTemplate.MONTHLY, day_of_month=31, start_on=date(2026, 1, 31))
        self.assertEqual(recurrence.first_occurrence(t), date(2026, 1, 31))
        self.assertEqual(recurrence.step(t, date(2026, 1, 31)), date(2026, 2, 28))
        self.assertEqual(recurrence.step(t, date(2026, 2, 28)), date(2026, 3, 31))

    # --- yearly ---
    def test_yearly(self):
        t = self._template(frequency=TaskTemplate.YEARLY, month_of_year=7, day_of_month=1, start_on=date(2026, 7, 1))
        self.assertEqual(recurrence.first_occurrence(t), date(2026, 7, 1))
        self.assertEqual(recurrence.step(t, date(2026, 7, 1)), date(2027, 7, 1))

    # --- window bounds ---
    def test_end_on_stops_occurrences(self):
        t = self._template(frequency=TaskTemplate.DAILY, start_on=date(2026, 1, 1), end_on=date(2026, 1, 5))
        self.assertIsNone(recurrence.occurrence_on_or_after(t, date(2026, 1, 6)))


class MaterializeTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(username="owner", password="pw")

    def _template(self, **kwargs):
        kwargs.setdefault("title", "Monthly filing")
        kwargs.setdefault("owner", self.user)
        return TaskTemplate.objects.create(**kwargs)

    def test_creates_task_copying_blueprint(self):
        t = self._template(
            description="do the thing",
            priority=TaskItem.HIGH,
            frequency=TaskTemplate.DAILY,
            start_on=date(2026, 1, 1),
        )
        task = recurrence.materialize_due_tasks(t, date(2026, 1, 1))
        self.assertIsNotNone(task)
        self.assertEqual(task.title, "Monthly filing")
        self.assertEqual(task.description, "do the thing")
        self.assertEqual(task.priority, TaskItem.HIGH)
        self.assertEqual(task.template_id, t.id)
        self.assertEqual(task.owner_id, self.user.id)
        self.assertEqual(task.end_date.date(), date(2026, 1, 1))
        t.refresh_from_db()
        self.assertEqual(t.last_generated_occurrence, date(2026, 1, 1))

    def test_idempotent_same_day(self):
        t = self._template(frequency=TaskTemplate.DAILY, start_on=date(2026, 1, 1))
        recurrence.materialize_due_tasks(t, date(2026, 1, 10))
        recurrence.materialize_due_tasks(t, date(2026, 1, 10))
        self.assertEqual(t.generated_tasks.count(), 1)

    def test_latest_missed_only(self):
        # Never generated, first run 10 days in → exactly one task, for the latest occurrence.
        t = self._template(frequency=TaskTemplate.DAILY, start_on=date(2026, 1, 1))
        recurrence.materialize_due_tasks(t, date(2026, 1, 10))
        self.assertEqual(t.generated_tasks.count(), 1)
        self.assertEqual(t.generated_tasks.get().end_date.date(), date(2026, 1, 10))

    def test_lead_time_brings_task_forward(self):
        # First occurrence Aug 1, 3-day lead time → eligible Jul 29, not Jul 28.
        t = self._template(frequency=TaskTemplate.MONTHLY, day_of_month=1, start_on=date(2026, 8, 1), lead_time_days=3)
        self.assertIsNone(recurrence.materialize_due_tasks(t, date(2026, 7, 28)))
        task = recurrence.materialize_due_tasks(t, date(2026, 7, 29))
        self.assertIsNotNone(task)
        self.assertEqual(task.end_date.date(), date(2026, 8, 1))

    def test_zero_lead_time_generates_on_due_date(self):
        t = self._template(frequency=TaskTemplate.MONTHLY, day_of_month=1, start_on=date(2026, 8, 1))
        self.assertIsNone(recurrence.materialize_due_tasks(t, date(2026, 7, 31)))
        task = recurrence.materialize_due_tasks(t, date(2026, 8, 1))
        self.assertEqual(task.end_date.date(), date(2026, 8, 1))

    def test_end_on_caps_generation(self):
        t = self._template(frequency=TaskTemplate.DAILY, start_on=date(2026, 1, 1), end_on=date(2026, 1, 5))
        task = recurrence.materialize_due_tasks(t, date(2026, 1, 10))
        self.assertEqual(task.end_date.date(), date(2026, 1, 5))

    def test_inactive_template_generates_nothing(self):
        t = self._template(frequency=TaskTemplate.DAILY, start_on=date(2026, 1, 1), is_active=False)
        self.assertIsNone(recurrence.materialize_due_tasks(t, date(2026, 1, 1)))

    def test_skip_if_previous_open_blocks_then_resumes(self):
        t = self._template(frequency=TaskTemplate.DAILY, start_on=date(2026, 1, 1), skip_if_previous_open=True)
        first = recurrence.materialize_due_tasks(t, date(2026, 1, 1))
        self.assertIsNotNone(first)

        # Previous still open → no new task, marker not advanced.
        self.assertIsNone(recurrence.materialize_due_tasks(t, date(2026, 1, 2)))
        self.assertEqual(t.generated_tasks.count(), 1)
        t.refresh_from_db()
        self.assertEqual(t.last_generated_occurrence, date(2026, 1, 1))

        # Complete it → generation resumes at the current occurrence.
        first.completed = True
        first.save()
        resumed = recurrence.materialize_due_tasks(t, date(2026, 1, 2))
        self.assertIsNotNone(resumed)
        self.assertEqual(t.generated_tasks.count(), 2)

    def test_generate_all_spans_templates(self):
        self._template(frequency=TaskTemplate.DAILY, start_on=date(2026, 1, 1), title="a")
        self._template(frequency=TaskTemplate.DAILY, start_on=date(2026, 1, 1), title="b")
        created = recurrence.generate_all(date(2026, 1, 1))
        self.assertEqual(len(created), 2)
