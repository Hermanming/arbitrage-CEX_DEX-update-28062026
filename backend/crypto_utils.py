"""Symmetric encryption helpers for sensitive credentials."""
import os
from cryptography.fernet import Fernet

_KEY = os.environ.get("FERNET_KEY", "").encode()
_CIPHER = Fernet(_KEY) if _KEY else None


def encrypt(plain: str) -> str:
    if not plain:
        return ""
    if _CIPHER is None:
        raise RuntimeError("FERNET_KEY not configured")
    return _CIPHER.encrypt(plain.encode()).decode()


def decrypt(token: str) -> str:
    if not token:
        return ""
    if _CIPHER is None:
        raise RuntimeError("FERNET_KEY not configured")
    return _CIPHER.decrypt(token.encode()).decode()


def mask(plain: str, keep: int = 4) -> str:
    if not plain:
        return ""
    if len(plain) <= keep * 2:
        return "*" * len(plain)
    return plain[:keep] + "*" * (len(plain) - keep * 2) + plain[-keep:]
