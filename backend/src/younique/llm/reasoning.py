from __future__ import annotations

from typing import Any


def translate_reasoning(control: str, enabled: bool, effort: str | None = None) -> dict[str, Any]:
    if control == "none" or not enabled:
        return {}
    if control == "boolean":
        return {"reasoning": {"enabled": True}}
    if control == "effort":
        return {"reasoning_effort": effort or "medium"}
    if control == "budget_tokens":
        return {"thinking": {"type": "enabled", "budget_tokens": 1024}}
    return {}
