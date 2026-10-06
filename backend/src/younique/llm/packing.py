from __future__ import annotations

from typing import Any


def pack_messages(messages: list[dict[str, Any]], *, budget_tokens: int) -> list[dict[str, Any]]:
    system = [m for m in messages if m.get("role") == "system"]
    rest = [m for m in messages if m.get("role") != "system"]
    kept: list[dict[str, Any]] = []
    used = sum(_estimate(m) for m in system)
    for message in reversed(rest):
        cost = _estimate(message)
        if used + cost > budget_tokens and kept:
            break
        kept.append(message)
        used += cost
    kept.reverse()
    paired = _drop_orphans(kept)
    return system + paired


def _estimate(message: dict[str, Any]) -> int:
    content = message.get("content") or ""
    return max(1, len(str(content)) // 4)


def _drop_orphans(messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    call_ids = {
        m.get("tool_call_id")
        for m in messages
        if m.get("role") == "assistant" and m.get("tool_call_id")
    }
    result_ids = {
        m.get("tool_call_id") for m in messages if m.get("role") == "tool" and m.get("tool_call_id")
    }
    paired = call_ids & result_ids
    cleaned: list[dict[str, Any]] = []
    for message in messages:
        tool_call_id = message.get("tool_call_id")
        if (
            tool_call_id
            and tool_call_id not in paired
            and message.get("role") in {"assistant", "tool"}
        ):
            continue
        cleaned.append(message)
    return cleaned
