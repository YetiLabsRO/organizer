"""The sync engine.

The tests that matter most are the ones a plausible-looking implementation still fails: status
changes VolunHub never timestamps, our own writes echoing back, the two-step reopen, a partial
listing, and removals that must never destroy local data.
"""

from datetime import UTC, datetime

from django.db import DEFAULT_DB_ALIAS, connections
from django.test import TestCase, override_settings

from integrations.volunhub import sync
from integrations.volunhub.locks import sync_lock_key
from integrations.volunhub.models import VolunHubConnection, VolunHubProjectLink, VolunHubTaskLink
from integrations.volunhub.tests.fakes import FakeVolunHub
from integrations.volunhub.tests.helpers import SETTINGS, make_connection, make_user
from tasks.models import Project, TaskItem


@override_settings(**SETTINGS)
class SyncTestCase(TestCase):
    def setUp(self):
        self.user = make_user()
        self.connection = make_connection(self.user)
        self.fake = FakeVolunHub()

    def run_sync(self):
        return sync.sync_connection(self.connection, api=self.fake)

    def local(self, external_id):
        return VolunHubTaskLink.objects.select_related("task").get(user=self.user, external_id=external_id).task

    def link(self, external_id):
        return VolunHubTaskLink.objects.get(user=self.user, external_id=external_id)


class ImportTests(SyncTestCase):
    def test_assigned_task_is_imported_with_mapped_fields(self):
        deadline = datetime(2026, 10, 20, 15, 0, tzinfo=UTC)
        task_id = self.fake.add_task(
            title="Order tents",
            description="Two **big** ones",
            deadline=deadline,
            estimated_time=90,
            priority=3,
            state="in_progress",
        )

        report = self.run_sync()

        self.assertEqual(report.created_locally, 1)
        task = self.local(task_id)
        self.assertEqual(task.owner, self.user)
        self.assertEqual(task.title, "Order tents")
        self.assertEqual(task.description, "Two **big** ones")
        self.assertEqual(task.end_date, deadline)
        self.assertEqual(task.estimated_time, 90)
        self.assertEqual(task.priority, TaskItem.HIGH)
        self.assertEqual(task.status, TaskItem.IN_PROGRESS)
        self.assertFalse(task.completed)

    def test_unassigned_tasks_are_not_imported(self):
        self.fake.add_task(assigned=False)
        self.run_sync()
        self.assertFalse(TaskItem.objects.exists())

    def test_finished_state_completes_the_task_despite_a_stale_completed_column(self):
        task_id = self.fake.add_task(state="finished")
        self.assertFalse(self.fake.serialize(task_id)["completed"])  # VolunHub's stale column

        self.run_sync()

        task = self.local(task_id)
        self.assertTrue(task.completed)
        # Not stamped "now": the import must not pile history onto today's statistics.
        self.assertEqual(task.completed_date, self.fake.tasks[task_id]["changed_date"])

    def test_draft_and_planned_both_import_as_idea(self):
        draft, planned = self.fake.add_task(state="draft"), self.fake.add_task(state="planned")
        self.run_sync()
        self.assertEqual(self.local(draft).status, TaskItem.IDEA)
        self.assertEqual(self.local(planned).status, TaskItem.IDEA)

    def test_second_run_without_changes_does_nothing(self):
        self.fake.add_task(title="Stable", deadline=datetime(2026, 11, 1, 8, 0, tzinfo=UTC))
        self.run_sync()
        self.fake.calls.clear()

        report = self.run_sync()

        self.assertEqual(report.updated_locally + report.pushed + report.conflicts, 0)
        self.assertEqual(self.fake.calls, [("list",)])

    def test_partial_listing_aborts_the_run(self):
        task_id = self.fake.add_task()
        self.run_sync()
        self.fake.fail_listing = True

        self.run_sync()

        self.assertEqual(self.link(task_id).state, VolunHubTaskLink.ACTIVE)
        self.connection.refresh_from_db()
        self.assertIn("502", self.connection.last_error)

    def test_needs_reauth_connection_is_skipped(self):
        self.fake.add_task()
        self.connection.mark_needs_reauth("expired")
        self.run_sync()
        self.assertEqual(self.fake.calls, [])


class RemoteChangeTests(SyncTestCase):
    def test_remote_content_edit_is_applied(self):
        task_id = self.fake.add_task(title="Old")
        self.run_sync()
        self.fake.edit(task_id, title="New")

        report = self.run_sync()

        self.assertEqual(report.updated_locally, 1)
        self.assertEqual(self.local(task_id).title, "New")

    def test_remote_status_change_is_seen_although_changed_date_did_not_move(self):
        task_id = self.fake.add_task(state="planned")
        self.run_sync()
        self.fake.transition(task_id, "blocked")

        self.run_sync()

        self.assertEqual(self.local(task_id).status, TaskItem.BLOCKED)

    def test_draft_to_planned_is_not_a_change(self):
        task_id = self.fake.add_task(state="draft")
        self.run_sync()
        self.fake.transition(task_id, "planned")
        self.fake.calls.clear()

        report = self.run_sync()

        self.assertEqual(report.updated_locally, 0)
        self.assertEqual(self.fake.calls, [("list",)])


class PushTests(SyncTestCase):
    def test_local_content_edit_pushes_only_the_changed_field(self):
        task_id = self.fake.add_task(title="Before", description="Keep me")
        self.run_sync()
        task = self.local(task_id)
        task.title = "After"
        task.save()

        report = self.run_sync()

        self.assertEqual(report.pushed, 1)
        self.assertEqual(self.fake.calls_of("patch"), [("patch", task_id, {"title": "After"})])
        self.assertEqual(self.fake.tasks[task_id]["title"], "After")

    def test_local_deadline_and_priority_map_to_volunhub_fields(self):
        task_id = self.fake.add_task()
        self.run_sync()
        task = self.local(task_id)
        task.end_date = datetime(2026, 12, 24, 10, 0, tzinfo=UTC)
        task.priority = TaskItem.HIGH
        task.save()

        self.run_sync()

        ((_, _, body),) = self.fake.calls_of("patch")
        self.assertEqual(body["priority"], 3)
        self.assertEqual(body["deadline"], "2026-12-24T10:00:00+00:00")
        self.assertNotIn("end_date", body)

    def test_own_write_is_not_echoed_back(self):
        task_id = self.fake.add_task(title="Before")
        self.run_sync()
        task = self.local(task_id)
        task.title = "After"
        task.save()
        self.run_sync()
        self.fake.calls.clear()

        report = self.run_sync()

        self.assertEqual(report.updated_locally + report.pushed, 0)
        self.assertEqual(self.fake.calls, [("list",)])

    def test_local_completion_is_pushed_as_finished(self):
        task_id = self.fake.add_task(state="in_progress")
        self.run_sync()
        task = self.local(task_id)
        task.completed = True
        task.save()

        self.run_sync()

        self.assertEqual(self.fake.calls_of("status"), [("status", task_id, "finished")])
        self.assertEqual(self.fake.tasks[task_id]["state"], "finished")

    def test_reopening_to_in_progress_goes_through_planned(self):
        task_id = self.fake.add_task(state="finished")
        self.run_sync()
        task = self.local(task_id)
        task.completed = False
        task.status = TaskItem.IN_PROGRESS
        task.save()

        self.run_sync()

        self.assertEqual(
            self.fake.calls_of("status"), [("status", task_id, "planned"), ("status", task_id, "in_progress")]
        )
        self.assertEqual(self.fake.tasks[task_id]["state"], "in_progress")

    def test_idea_on_a_draft_task_is_not_pushed(self):
        self.fake.add_task(state="draft")
        self.run_sync()
        self.run_sync()
        self.assertEqual(self.fake.calls_of("status"), [])

    def test_given_up_is_never_pushed_nor_overwritten(self):
        task_id = self.fake.add_task(state="in_progress")
        self.run_sync()
        task = self.local(task_id)
        task.status = TaskItem.GIVEN_UP
        task.save()
        self.run_sync()
        self.fake.transition(task_id, "blocked")

        self.run_sync()

        self.assertEqual(self.fake.calls_of("status"), [])
        self.assertEqual(self.local(task_id).status, TaskItem.GIVEN_UP)

    def test_unreachable_transition_is_recorded_and_the_run_continues(self):
        stuck = self.fake.add_task(state="planned")
        other = self.fake.add_task(title="Other")
        self.run_sync()
        task = self.local(stuck)
        task.completed = True
        task.save()
        renamed = self.local(other)
        renamed.title = "Other renamed"
        renamed.save()
        self.fake.refuse_states.add("finished")

        report = self.run_sync()

        self.assertEqual(report.errors, 1)
        self.assertIn("409", self.link(stuck).last_error)
        self.assertEqual(self.fake.tasks[other]["title"], "Other renamed")
        # Retried next run: the snapshot still holds the old state.
        self.fake.calls.clear()
        self.run_sync()
        self.assertEqual(self.fake.calls_of("status"), [("status", stuck, "finished")])


class ConflictTests(SyncTestCase):
    def test_conflicting_edits_keep_the_organizer_value(self):
        task_id = self.fake.add_task(title="Base")
        self.run_sync()
        self.fake.edit(task_id, title="Theirs")
        task = self.local(task_id)
        task.title = "Ours"
        task.save()

        report = self.run_sync()

        self.assertEqual(report.conflicts, 1)
        self.assertEqual(self.local(task_id).title, "Ours")
        self.assertEqual(self.fake.tasks[task_id]["title"], "Ours")

    def test_same_change_on_both_sides_is_not_a_conflict(self):
        task_id = self.fake.add_task(title="Base")
        self.run_sync()
        self.fake.edit(task_id, title="Same")
        task = self.local(task_id)
        task.title = "Same"
        task.save()

        report = self.run_sync()

        self.assertEqual(report.conflicts, 0)
        self.assertEqual(self.fake.calls_of("patch"), [])

    def test_different_fields_merge(self):
        task_id = self.fake.add_task(title="Base", estimated_time=30)
        self.run_sync()
        self.fake.edit(task_id, estimated_time=45)
        task = self.local(task_id)
        task.title = "Renamed here"
        task.save()

        self.run_sync()

        self.assertEqual(self.local(task_id).estimated_time, 45)
        self.assertEqual(self.fake.tasks[task_id]["title"], "Renamed here")
        self.assertEqual(self.fake.tasks[task_id]["estimated_time"], 45)


class ContentPushDisabledTests(SyncTestCase):
    def test_forbidden_patch_disables_content_push_but_status_still_flows(self):
        task_id = self.fake.add_task(state="planned", title="Base")
        self.run_sync()
        self.fake.forbid_patch = True
        task = self.local(task_id)
        task.title = "Local title"
        task.status = TaskItem.BLOCKED
        task.save()

        self.run_sync()

        self.connection.refresh_from_db()
        self.assertFalse(self.connection.content_push_enabled)
        self.assertIn("403", self.connection.last_error)
        self.assertEqual(self.fake.tasks[task_id]["state"], "blocked")

    def test_with_content_push_disabled_volunhub_wins_content(self):
        task_id = self.fake.add_task(title="Base")
        self.run_sync()
        self.connection.disable_content_push("refused")
        task = self.local(task_id)
        task.title = "Local"
        task.save()
        self.run_sync()
        self.assertEqual(self.fake.calls_of("patch"), [])
        self.assertEqual(self.local(task_id).title, "Local")  # kept until VolunHub changes it

        self.fake.edit(task_id, title="Remote")
        self.run_sync()

        self.assertEqual(self.local(task_id).title, "Remote")

    def test_read_only_connection_pushes_nothing(self):
        self.connection.granted_scope = "mcp:tasks:read"
        self.connection.save()
        task_id = self.fake.add_task(state="planned")
        self.run_sync()
        task = self.local(task_id)
        task.title = "Changed"
        task.completed = True
        task.save()

        self.run_sync()

        self.assertEqual(self.fake.calls_of("patch") + self.fake.calls_of("status"), [])


class RemovalTests(SyncTestCase):
    def test_unassigned_task_is_kept_and_marked(self):
        task_id = self.fake.add_task(title="Gone from my list")
        self.run_sync()
        self.fake.unassign(task_id)

        report = self.run_sync()

        self.assertEqual(report.removed, 1)
        link = self.link(task_id)
        self.assertEqual((link.state, link.removed_reason), (VolunHubTaskLink.REMOVED, VolunHubTaskLink.UNASSIGNED))
        self.assertEqual(link.task.title, "Gone from my list")

    def test_deleted_task_is_kept_and_marked(self):
        task_id = self.fake.add_task()
        self.run_sync()
        self.fake.delete(task_id)

        self.run_sync()

        link = self.link(task_id)
        self.assertEqual(link.removed_reason, VolunHubTaskLink.DELETED)
        self.assertTrue(TaskItem.objects.filter(pk=link.task_id).exists())

    def test_lookup_failure_changes_nothing(self):
        task_id = self.fake.add_task()
        self.run_sync()
        self.fake.unassign(task_id)
        self.fake.lookup_error = True

        self.run_sync()

        self.assertEqual(self.link(task_id).state, VolunHubTaskLink.ACTIVE)

    def test_reassigned_task_is_reattached_without_a_duplicate(self):
        task_id = self.fake.add_task(title="Boomerang")
        self.run_sync()
        local_pk = self.local(task_id).pk
        self.fake.unassign(task_id)
        self.run_sync()
        self.fake.assigned.add(task_id)

        report = self.run_sync()

        self.assertEqual(report.reattached, 1)
        self.assertEqual(self.link(task_id).state, VolunHubTaskLink.ACTIVE)
        self.assertEqual(self.local(task_id).pk, local_pk)
        self.assertEqual(TaskItem.objects.count(), 1)

    def test_local_delete_is_never_reimported_nor_deleted_upstream(self):
        task_id = self.fake.add_task()
        self.run_sync()
        self.local(task_id).delete()

        self.run_sync()

        self.assertFalse(TaskItem.objects.exists())
        self.assertIn(task_id, self.fake.tasks)
        self.assertTrue(self.link(task_id).is_tombstone)

    def test_tombstone_is_dropped_once_the_task_leaves_the_listing(self):
        task_id = self.fake.add_task()
        self.run_sync()
        self.local(task_id).delete()
        self.fake.unassign(task_id)

        self.run_sync()

        self.assertFalse(VolunHubTaskLink.objects.exists())


class ProjectTests(SyncTestCase):
    def test_unknown_project_is_auto_created(self):
        task_id = self.fake.add_task(project=(7, "jamboree", "Jamboree 2027"))

        self.run_sync()

        project = self.local(task_id).project
        self.assertEqual(project.title, "Jamboree 2027")
        self.assertTrue(VolunHubProjectLink.objects.get(external_id=7).auto_created)

    def test_project_is_shared_by_every_task_and_user(self):
        first = self.fake.add_task(project=(7, "j", "Jamboree"))
        second = self.fake.add_task(project=(7, "j", "Jamboree"))
        self.run_sync()
        other_user = make_user("other")
        other = make_connection(other_user)
        other_fake = FakeVolunHub()
        other_fake.add_task(project=(7, "j", "Jamboree"))
        sync.sync_connection(other, api=other_fake)

        self.assertEqual(Project.objects.count(), 1)
        self.assertEqual(self.local(first).project, self.local(second).project)

    def test_auto_created_project_follows_renames(self):
        task_id = self.fake.add_task(project=(7, "j", "Old name"))
        self.run_sync()
        self.fake.edit(task_id, project=(7, "j", "New name"))

        self.run_sync()

        self.assertEqual(self.local(task_id).project.title, "New name")

    def test_project_move_in_volunhub_is_applied(self):
        task_id = self.fake.add_task(project=(7, "a", "A"))
        self.run_sync()
        self.fake.edit(task_id, project=(8, "b", "B"))

        self.run_sync()

        self.assertEqual(self.local(task_id).project.title, "B")

    def test_local_project_move_is_kept_and_not_pushed(self):
        task_id = self.fake.add_task(project=(7, "a", "A"))
        self.run_sync()
        mine = Project.objects.create(title="Mine")
        task = self.local(task_id)
        task.project = mine
        task.save()

        self.run_sync()

        self.assertEqual(self.local(task_id).project, mine)
        self.assertEqual(self.fake.calls_of("patch"), [])

    def test_locally_deleted_project_is_not_recreated(self):
        task_id = self.fake.add_task(project=(7, "a", "A"))
        self.run_sync()
        self.local(task_id).project.delete()
        new_id = self.fake.add_task(project=(7, "a", "A"))

        self.run_sync()

        self.assertIsNone(self.local(new_id).project)
        self.assertFalse(Project.objects.exists())


class LockTests(SyncTestCase):
    def test_overlapping_run_is_skipped(self):
        self.fake.add_task()
        # Another worker = another database session holding the advisory lock.
        other = connections.create_connection(DEFAULT_DB_ALIAS)
        try:
            with other.cursor() as cursor:
                cursor.execute("SELECT pg_advisory_lock(%s, %s)", sync_lock_key(self.connection.pk))
            report = self.run_sync()
        finally:
            other.close()

        self.assertTrue(report.skipped)
        self.assertEqual(self.fake.calls, [])

    def test_lock_is_released_after_a_run(self):
        self.run_sync()
        self.assertFalse(self.run_sync().skipped)


@override_settings(**SETTINGS)
class ConnectionStatusTests(TestCase):
    def test_auth_failure_during_listing_leaves_needs_reauth(self):
        from integrations.volunhub.exceptions import VolunHubAuthError

        user = make_user()
        connection = make_connection(user)
        fake = FakeVolunHub()

        def expired():
            connection.mark_needs_reauth("invalid_grant")
            raise VolunHubAuthError("invalid_grant")

        fake.list_assigned_tasks = expired

        sync.sync_connection(connection, api=fake)

        connection.refresh_from_db()
        self.assertEqual(connection.status, VolunHubConnection.NEEDS_REAUTH)
