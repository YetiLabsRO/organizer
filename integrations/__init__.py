"""Clients for third-party services Organizer syncs with.

Each sub-package is a self-contained Django app owning its own models, OAuth client and sync
engine (see ``integrations.notion``). Shared plumbing that is genuinely provider-agnostic lives
here at the top level — currently just ``crypto`` (Fernet helpers for credential storage).
"""
