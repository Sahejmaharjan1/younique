from __future__ import annotations

from typing import Any, Literal

Gate = Literal["allow", "deny", "approve"]


def default_mode(risk: str) -> str:
    if risk == "low":
        return "always_allow"
    return "ask_each_time"


def gate_tool(
    *,
    tool_key: str,
    risk: str,
    mode: str | None,
    allow_when_tainted: bool,
    trust_level: str,
    allowlist: set[str],
    method: str | None = None,
    host_allowlisted: bool = True,
) -> tuple[Gate, str]:
    if tool_key not in allowlist:
        return "deny", "policy"
    resolved = mode or default_mode(risk)
    if resolved == "never":
        return "deny", "policy"
    if method in {"POST", "PUT", "PATCH"} and not host_allowlisted:
        return "deny", "policy"
    tainted = trust_level == "untrusted"
    if tainted and risk == "high" and not allow_when_tainted:
        return "approve", "taint"
    if tainted and method in {"POST", "PUT", "PATCH"} and tool_key.startswith("http."):
        return "approve", "taint"
    if resolved == "ask_each_time":
        return "approve", "policy"
    return "allow", "policy"


def tool_output_changes_policy(output: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in output.items() if key != "tool_policy"}
