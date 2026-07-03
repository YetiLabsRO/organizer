"""Celery application for the organizer project.

Scheduling is driven by celery beat (see ``CELERY_BEAT_SCHEDULE`` in ``settings.py``), which invokes
``tasks.tasks.generate_recurring_tasks`` daily to materialize due recurring tasks. The REST API does
not depend on Celery — if the broker/workers are down, only automatic generation pauses.
"""

import os

from celery import Celery

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "organizer.settings")

app = Celery("organizer")
# Read CELERY_* settings from Django settings; discover @shared_task modules in installed apps.
app.config_from_object("django.conf:settings", namespace="CELERY")
app.autodiscover_tasks()
