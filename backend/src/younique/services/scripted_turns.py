from __future__ import annotations

from typing import Any


def scripted_turns(
    text: str, turns: list[dict[str, Any]] | None, *, llm_mode: str
) -> list[dict[str, Any]]:
    if turns:
        return turns
    if llm_mode != "fake":
        return [{"text": "Hello from Younique.", "tool_calls": []}]
    lowered = text.lower()
    if "gmail" in lowered and ("send" in lowered or "email" in lowered):
        return [
            {
                "text": "",
                "tool_calls": [
                    {
                        "id": "call-gmail",
                        "name": "gmail.send_email",
                        "arguments": {
                            "to": "ops@example.com",
                            "mailbox": "me",
                            "raw": text,
                            "body": text,
                        },
                    }
                ],
            }
        ]
    if "send" in lowered and "email" in lowered:
        return [
            {
                "text": "I'll send that email.",
                "tool_calls": [
                    {
                        "id": "call-smtp",
                        "name": "smtp.send",
                        "arguments": {"to": "ops@example.com", "subject": "Report", "body": text},
                    }
                ],
            }
        ]
    if lowered.startswith("stream "):
        return [
            {
                "text": "token " * 200,
                "reasoning": "Drafting a longer answer before sending tokens.",
                "tool_calls": [],
            }
        ]
    return [{"text": "Hello from Younique.", "tool_calls": []}]


def without_reasoning(turns: list[dict[str, Any]]) -> list[dict[str, Any]]:
    stripped: list[dict[str, Any]] = []
    for turn in turns:
        copy = dict(turn)
        copy["reasoning"] = ""
        stripped.append(copy)
    return stripped


def refusal_from(result: dict[str, Any]) -> str | None:
    messages = result.get("messages")
    if not isinstance(messages, list):
        return None
    for message in messages:
        if not isinstance(message, dict):
            continue
        content = str(message.get("content") or "")
        if message.get("role") == "tool" and "blocked by policy" in content:
            return content
    return None
