"""Postgres advisory locks for the VolunHub integration.

Two things must never run twice at once: registering the instance's OAuth client (each DCR call
creates a client record in VolunHub), and syncing one connection (a beat run and a "Sync now" would
otherwise push the same change twice). Advisory locks need no extra table and are released by
Postgres if the worker dies.
"""

from contextlib import contextmanager

from django.db import connection

# First key of the two-int advisory lock space, so these never collide with anyone else's locks.
_NAMESPACE = 0x56484221  # "VHB!"
_REGISTRATION = 0
_SYNC_OFFSET = 1  # sync locks use connection pk + offset as the second key


def lock_registration():
    """Block until this transaction holds the registration lock. Released at commit/rollback."""
    with connection.cursor() as cursor:
        cursor.execute("SELECT pg_advisory_xact_lock(%s, %s)", [_NAMESPACE, _REGISTRATION])


def sync_lock_key(connection_pk):
    return _NAMESPACE, (connection_pk + _SYNC_OFFSET) % 2**31


@contextmanager
def sync_lock(connection_pk):
    """Try to take the per-connection sync lock without waiting. Yields whether it was acquired."""
    key = sync_lock_key(connection_pk)
    with connection.cursor() as cursor:
        cursor.execute("SELECT pg_try_advisory_lock(%s, %s)", key)
        acquired = cursor.fetchone()[0]
    try:
        yield acquired
    finally:
        if acquired:
            with connection.cursor() as cursor:
                cursor.execute("SELECT pg_advisory_unlock(%s, %s)", key)
