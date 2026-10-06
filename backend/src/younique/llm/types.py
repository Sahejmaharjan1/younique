from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


class ToolCall(BaseModel):
    id: str
    name: str
    arguments: dict[str, Any] = Field(default_factory=dict)


class StreamEvent(BaseModel):
    kind: Literal["text", "reasoning", "tool_call", "usage", "done", "error"]
    text: str = ""
    tool_call: ToolCall | None = None
    input_tokens: int = 0
    cached_input_tokens: int = 0
    output_tokens: int = 0
    reasoning_tokens: int = 0
    error_code: str | None = None


class ModelTurn(BaseModel):
    text: str = ""
    reasoning: str = ""
    tool_calls: list[ToolCall] = Field(default_factory=list)
    input_tokens: int = 10
    output_tokens: int = 5
    cached_input_tokens: int = 0
    reasoning_tokens: int = 0


class PriceSnapshot(BaseModel):
    input_micro_usd_per_mtok: int
    output_micro_usd_per_mtok: int
    cached_input_micro_usd_per_mtok: int
    reasoning_micro_usd_per_mtok: int
