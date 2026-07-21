from django.apps import AppConfig


class TasksConfig(AppConfig):
    name = "tasks"

    def ready(self):
        # Wire up the real-time task-sync signal handlers (post_save/post_delete on TaskItem).
        # Imported here so registration happens exactly once, after the app registry is ready.
        from tasks import signals  # noqa: F401
