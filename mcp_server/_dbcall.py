"""Run blocking ORM work off the event loop while managing the DB connection.

MCP tool and token-verification code runs outside Django's request/response cycle, so nothing
else closes the thread-local database connection that ``sync_to_async`` opens on its worker
thread. Cycling the connection around each call mirrors Django's per-request behaviour (honouring
``CONN_MAX_AGE``) and prevents leaked/stale connections.
"""

from asgiref.sync import sync_to_async
from django.db import close_old_connections


async def db_call(fn, /, *args, **kwargs):
    def _wrapped():
        close_old_connections()
        try:
            return fn(*args, **kwargs)
        finally:
            close_old_connections()

    return await sync_to_async(_wrapped, thread_sensitive=True)()
