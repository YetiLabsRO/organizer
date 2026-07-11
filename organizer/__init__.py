# Ensure the Celery app is loaded when Django starts so @shared_task decorators bind to it.
from organizer.celery import app as celery_app

__all__ = ("celery_app",)
