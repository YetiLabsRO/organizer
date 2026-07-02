"""Inspect or backfill task ownership.

Owner scoping (``TaskItemViewSet`` filters ``owner=request.user``) hides tasks that
carry no owner or a different owner than the logged-in user. Historically the API
never set ``owner`` on create, so app-created tasks have ``owner IS NULL``.

Run with no target user to see the current distribution (safe, read-only). Pass
``--email``/``--username`` plus ``--apply`` to reassign. Reassignment uses a bulk
``UPDATE`` (it does not trigger ``TaskItem.save()`` side effects).

Examples::

    # 1) See who owns what (and the exact usernames/emails to target):
    python manage.py backfill_task_owner

    # 2) Preview claiming every task for an account:
    python manage.py backfill_task_owner --email you@example.com

    # 3) Actually do it (only the orphaned/NULL-owner ones):
    python manage.py backfill_task_owner --email you@example.com --only-unowned --apply
"""

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError
from django.db.models import Count

from tasks.models import TaskItem


class Command(BaseCommand):
    help = "Report or backfill task ownership (dry run unless --apply is given)."

    def add_arguments(self, parser):
        parser.add_argument("--email", help="Target user's email (case-insensitive).")
        parser.add_argument("--username", help="Target user's username.")
        parser.add_argument(
            "--only-unowned",
            action="store_true",
            help="Reassign only tasks whose owner is NULL (default: all tasks).",
        )
        parser.add_argument(
            "--apply",
            action="store_true",
            help="Write the change. Without it the command only reports (dry run).",
        )

    def _report_distribution(self, User):
        total = TaskItem.objects.count()
        unowned = TaskItem.objects.filter(owner__isnull=True).count()
        self.stdout.write(f"Total tasks: {total}  (unowned/NULL: {unowned})")
        self.stdout.write("Ownership distribution:")
        counts = {
            row["owner"]: row["n"]
            for row in TaskItem.objects.values("owner").order_by().annotate(n=Count("id"))
        }
        names = {u.pk: (u.username, u.email) for u in User.objects.all()}
        for owner_id, n in sorted(counts.items(), key=lambda kv: -kv[1]):
            if owner_id is None:
                label = "<unowned / NULL>"
            else:
                uname, uemail = names.get(owner_id, ("<deleted user>", ""))
                label = f"id={owner_id} username={uname!r} email={uemail!r}"
            self.stdout.write(f"  {n:>8}  {label}")

    def _resolve_user(self, User, email, username):
        qs = User.objects.all()
        if username:
            qs = qs.filter(username=username)
        if email:
            qs = qs.filter(email__iexact=email)
        users = list(qs)
        if not users:
            raise CommandError("No user matches the given --email/--username.")
        if len(users) > 1:
            matches = ", ".join(
                f"id={u.pk} username={u.username!r} email={u.email!r}" for u in users
            )
            raise CommandError(f"Multiple users match; narrow it down: {matches}")
        return users[0]

    def handle(self, *args, **opts):
        User = get_user_model()
        self._report_distribution(User)

        if not (opts["email"] or opts["username"]):
            self.stdout.write(
                "\nNo --email/--username given, so nothing will change. Re-run with "
                "--email you@example.com [--only-unowned] --apply to reassign."
            )
            return

        user = self._resolve_user(User, opts["email"], opts["username"])
        qs = TaskItem.objects.all()
        if opts["only_unowned"]:
            qs = qs.filter(owner__isnull=True)
        n = qs.count()

        if not opts["apply"]:
            self.stdout.write(
                self.style.WARNING(
                    f"\nDRY RUN: would set owner -> id={user.pk} username={user.username!r} "
                    f"on {n} task(s). Re-run with --apply to write."
                )
            )
            return

        updated = qs.update(owner=user)
        self.stdout.write(
            self.style.SUCCESS(
                f"\nAssigned {updated} task(s) to id={user.pk} username={user.username!r}."
            )
        )
