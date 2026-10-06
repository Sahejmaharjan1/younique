from __future__ import annotations

import time
from typing import Any


def limit_error(state: dict[str, Any]) -> str | None:
    if state.get("cancel_requested"):
        return "run_cancelled"
    if int(state.get("step_count") or 0) >= int(state.get("max_steps") or 25):
        return "graph_step_limit_exceeded"
    if int(state.get("tool_call_count") or 0) >= int(state.get("max_tool_calls") or 50):
        return "graph_step_limit_exceeded"
    spent = int(state.get("spent_micro_usd") or 0)
    budget = int(state.get("budget_micro_usd") or 0)
    if budget and spent >= budget:
        return "budget_exceeded"
    deadline = float(state.get("deadline_epoch") or 0)
    if deadline and time.time() > deadline:
        return "run_timeout"
    return None
