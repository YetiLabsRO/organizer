"""Field mapping, state parsing and route planning."""

from datetime import UTC, datetime

from django.test import SimpleTestCase

from integrations.volunhub import mapping
from tasks.models import TaskItem


class StateTests(SimpleTestCase):
    def test_labels_parse_to_slugs(self):
        for label, slug in mapping.STATE_LABELS.items():
            with self.subTest(label=label):
                self.assertEqual(mapping.remote_state({"state_name": label}), slug)

    def test_slug_is_preferred_when_volunhub_sends_it(self):
        self.assertEqual(mapping.remote_state({"state": "blocked", "state_name": "Planificat"}), "blocked")

    def test_empty_or_unknown_label_means_no_workflow(self):
        self.assertIsNone(mapping.remote_state({"state_name": ""}))
        self.assertIsNone(mapping.remote_state({"state_name": "Arhivat"}))

    def test_local_state_covers_every_status(self):
        cases = {
            (TaskItem.IDEA, False): mapping.PLANNED,
            (TaskItem.IN_PROGRESS, False): mapping.IN_PROGRESS,
            (TaskItem.BLOCKED, False): mapping.BLOCKED,
            (TaskItem.GIVEN_UP, False): mapping.GIVEN_UP,
            (TaskItem.BLOCKED, True): mapping.FINISHED,
        }
        for (status, completed), expected in cases.items():
            with self.subTest(status=status, completed=completed):
                self.assertEqual(mapping.local_state(TaskItem(status=status, completed=completed)), expected)

    def test_apply_state(self):
        task = TaskItem(status=TaskItem.IN_PROGRESS, completed=True)
        mapping.apply_to_task(task, {mapping.STATE: mapping.BLOCKED})
        self.assertEqual((task.status, task.completed), (TaskItem.BLOCKED, False))

        mapping.apply_to_task(task, {mapping.STATE: mapping.FINISHED})
        self.assertEqual((task.status, task.completed), (TaskItem.BLOCKED, True))


class RouteTests(SimpleTestCase):
    def test_direct_transitions(self):
        self.assertEqual(mapping.route("planned", "in_progress"), ["in_progress"])
        self.assertEqual(mapping.route("draft", "finished"), ["finished"])
        self.assertEqual(mapping.route("blocked", "in_progress"), ["in_progress"])

    def test_detours_through_planned(self):
        self.assertEqual(mapping.route("draft", "in_progress"), ["planned", "in_progress"])
        self.assertEqual(mapping.route("finished", "in_progress"), ["planned", "in_progress"])
        self.assertEqual(mapping.route("finished", "blocked"), ["planned", "blocked"])

    def test_every_planned_route_is_valid(self):
        for current in mapping.STATES:
            for target in (mapping.PLANNED, mapping.IN_PROGRESS, mapping.BLOCKED, mapping.FINISHED):
                state = current
                for step in mapping.route(current, target):
                    with self.subTest(current=current, target=target, step=step):
                        self.assertIn(step, mapping.TRANSITIONS[state])
                    state = step
                self.assertEqual(state, target)

    def test_same_state_needs_no_call(self):
        self.assertEqual(mapping.route("blocked", "blocked"), [])


class ValueTests(SimpleTestCase):
    def test_timezone_only_difference_is_equal(self):
        remote = mapping.remote_values({"deadline": "2026-10-20T18:00:00+03:00", "state_name": ""})
        local = mapping.local_values(TaskItem(title="", end_date=datetime(2026, 10, 20, 15, 0, tzinfo=UTC)))
        self.assertEqual(remote["end_date"], local["end_date"])

    def test_blank_descriptions_and_line_endings_normalize(self):
        self.assertEqual(mapping.remote_values({"description": None})["description"], "")
        self.assertEqual(mapping.remote_values({"description": "a\r\nb"})["description"], "a\nb")
        self.assertEqual(mapping.local_values(TaskItem(description=None))["description"], "")

    def test_priority_round_trips(self):
        for remote, local in ((1, TaskItem.LOW), (2, TaskItem.NORMAL), (3, TaskItem.HIGH)):
            with self.subTest(remote=remote):
                self.assertEqual(mapping.remote_values({"priority": remote})["priority"], local)
                self.assertEqual(mapping.to_remote_payload({"priority": local}), {"priority": remote})

    def test_volunhub_end_date_is_not_the_deadline(self):
        values = mapping.remote_values({"end_date": "2026-10-20T18:00:00+03:00", "deadline": None})
        self.assertIsNone(values["end_date"])

    def test_payload_renames_end_date_to_deadline(self):
        self.assertEqual(mapping.to_remote_payload({"end_date": None}), {"deadline": None})

    def test_values_are_json_serializable(self):
        import json

        values = mapping.remote_values(
            {"title": "x", "start_date": "2026-10-01T09:00:00.123456+03:00", "state_name": "În lucru"}
        )
        self.assertEqual(json.loads(json.dumps(values)), values)
