from django.apps import AppConfig


class NotionConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "integrations.notion"
    # Without an explicit label Django would derive "notion" from the last path segment anyway,
    # but pinning it keeps migrations and `manage.py test integrations.notion` stable if the
    # package ever moves.
    label = "notion"
    verbose_name = "Notion sync"
