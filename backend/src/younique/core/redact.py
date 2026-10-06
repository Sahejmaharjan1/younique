from __future__ import annotations

import re
from typing import Any

SENSITIVE_KEYS = {
    "authorization",
    "api_key",
    "access_token",
    "refresh_token",
    "client_secret",
    "password",
    "token",
    "secret",
    "cookie",
    "key_ct",
    "dek_wrapped",
    "id_token",
    "private_key",
    "master_key",
    "smtp_password",
}

SECRET_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"sk-ant-api\d{2}-[\w-]{20,}"),
    re.compile(r"sk-proj-[\w-]{20,}"),
    re.compile(r"sk-[A-Za-z0-9]{32,}"),
    re.compile(r"gh[pousr]_[A-Za-z0-9]{36,}"),
    re.compile(r"xox[baprs]-[A-Za-z0-9-]{10,}"),
    re.compile(r"ya29\.[\w.-]+"),
    re.compile(r"AIza[\w-]{35}"),
    re.compile(r"yq_pat_[A-Za-z0-9]{32,}"),
    re.compile(r"eyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}"),
)


def redact_text(value: str) -> str:
    redacted = value
    for pattern in SECRET_PATTERNS:
        redacted = pattern.sub("[redacted:secret]", redacted)
    return redacted


def redact_value(value: Any, key: str | None = None) -> Any:
    if key is not None and key.lower() in SENSITIVE_KEYS:
        return f"[redacted:{key.lower()}]"
    if isinstance(value, str):
        return redact_text(value)
    if isinstance(value, dict):
        return {str(k): redact_value(v, str(k)) for k, v in value.items()}
    if isinstance(value, list):
        return [redact_value(item, key) for item in value]
    return value


def redact_event(_logger: Any, _method: str, event_dict: dict[str, Any]) -> dict[str, Any]:
    cleaned: dict[str, Any] = {}
    for key, value in event_dict.items():
        cleaned[key] = redact_value(value, key)
    if "event" in cleaned and isinstance(cleaned["event"], str):
        cleaned["event"] = redact_text(cleaned["event"])
    return cleaned
