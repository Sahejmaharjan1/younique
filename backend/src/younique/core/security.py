from __future__ import annotations

import hashlib
import secrets


def new_token(nbytes: int = 32) -> str:
    return secrets.token_urlsafe(nbytes)


def sha256_hex(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def session_cookie(token: str, *, secure: bool) -> str:
    name = "__Host-session" if secure else "session"
    parts = [f"{name}={token}", "HttpOnly", "Path=/", "SameSite=Lax", "Max-Age=2592000"]
    if secure:
        parts.append("Secure")
    return "; ".join(parts)


def csrf_cookie(token: str, *, secure: bool) -> str:
    parts = [f"csrf={token}", "Path=/", "SameSite=Lax", "Max-Age=2592000"]
    if secure:
        parts.append("Secure")
    return "; ".join(parts)


def clear_session_cookie(*, secure: bool) -> str:
    name = "__Host-session" if secure else "session"
    parts = [f"{name}=", "HttpOnly", "Path=/", "SameSite=Lax", "Max-Age=0"]
    if secure:
        parts.append("Secure")
    return "; ".join(parts)
