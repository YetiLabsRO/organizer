from django.apps import AppConfig


class VolunHubConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "integrations.volunhub"
    # Pinned so migrations and `manage.py test integrations.volunhub` stay stable if the package moves.
    label = "volunhub"
    verbose_name = "VolunHub sync"
