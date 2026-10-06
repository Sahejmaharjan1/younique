from __future__ import annotations

from typing import Any

_messages: list[dict[str, Any]] = []


def record(message: dict[str, Any]) -> None:
    _messages.append(dict(message))


def snapshot() -> list[dict[str, Any]]:
    return [dict(item) for item in _messages]


def clear() -> None:
    _messages.clear()
