from __future__ import annotations

from collections.abc import Callable
from typing import Any, Literal


def tool(
    *,
    key: str,
    title: str,
    description: str,
    risk: Literal["low", "medium", "high"],
    bundle: str,
) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
    def decorate(fn: Callable[..., Any]) -> Callable[..., Any]:
        fn.__tool_key__ = key  # type: ignore[attr-defined]
        fn.__tool_title__ = title  # type: ignore[attr-defined]
        fn.__tool_description__ = description  # type: ignore[attr-defined]
        fn.__tool_risk__ = risk  # type: ignore[attr-defined]
        fn.__tool_bundle__ = bundle  # type: ignore[attr-defined]
        return fn

    return decorate
