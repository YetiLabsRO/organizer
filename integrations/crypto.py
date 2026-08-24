"""Symmetric encryption for third-party credentials stored at rest.

Integrations persist OAuth access/refresh tokens, which are live credentials to a user's account on
another service. They are encrypted with Fernet (AES-128-CBC + HMAC, from ``cryptography``) so a
database dump alone does not hand over those accounts.

The key comes from ``INTEGRATIONS_TOKEN_KEY`` — deliberately named for all integrations rather than
any one of them, so sibling providers reuse it. When unset (dev, tests, CI) a key is derived from
``SECRET_KEY`` so nothing has to be configured to run the suite; that fallback is fine locally and
wrong in production, where rotating ``SECRET_KEY`` would silently strand every stored token.
"""

import base64
import hashlib

from cryptography.fernet import Fernet, InvalidToken
from django.conf import settings
from django.core.exceptions import ImproperlyConfigured

__all__ = ["encrypt", "decrypt", "InvalidToken"]


def _derive_key_from_secret() -> bytes:
    """A stable Fernet key derived from SECRET_KEY, for development and tests only."""
    digest = hashlib.sha256(settings.SECRET_KEY.encode("utf-8")).digest()
    return base64.urlsafe_b64encode(digest)


def _fernet() -> Fernet:
    configured = getattr(settings, "INTEGRATIONS_TOKEN_KEY", "") or ""
    if not configured:
        return Fernet(_derive_key_from_secret())
    try:
        return Fernet(configured.encode("utf-8") if isinstance(configured, str) else configured)
    except (ValueError, TypeError) as exc:
        raise ImproperlyConfigured(
            "INTEGRATIONS_TOKEN_KEY is not a valid Fernet key. Generate one with: "
            "python -c 'from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())'"
        ) from exc


def encrypt(value: str | None) -> str:
    """Encrypt ``value`` for storage. Empty/None round-trips as an empty string."""
    if not value:
        return ""
    return _fernet().encrypt(value.encode("utf-8")).decode("ascii")


def decrypt(value: str | None) -> str:
    """Decrypt a value produced by :func:`encrypt`. Returns "" for empty input.

    Raises ``cryptography.fernet.InvalidToken`` when the ciphertext does not match the current key —
    which is what a rotated key or a tampered row looks like, and is worth failing loudly on.
    """
    if not value:
        return ""
    return _fernet().decrypt(value.encode("ascii")).decode("utf-8")
