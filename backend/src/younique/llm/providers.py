from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any, Protocol

import httpx

from younique.llm.errors import normalize_provider_error
from younique.llm.types import ModelTurn, StreamEvent, ToolCall


class LLMProvider(Protocol):
    async def stream(
        self,
        *,
        model: str,
        messages: list[dict[str, Any]],
        api_key: str,
        base_url: str | None = None,
    ) -> AsyncIterator[StreamEvent]: ...

    async def validate_key(self, api_key: str, base_url: str | None = None) -> bool: ...


class FakeChatModel:
    def __init__(self, turns: list[ModelTurn] | None = None) -> None:
        self.turns = list(turns or [ModelTurn(text="Hello from Younique.")])
        self.calls = 0

    async def stream(
        self,
        *,
        model: str,
        messages: list[dict[str, Any]],
        api_key: str,
        base_url: str | None = None,
    ) -> AsyncIterator[StreamEvent]:
        self.calls += 1
        turn = self.turns.pop(0) if self.turns else ModelTurn(text="")
        if turn.reasoning:
            yield StreamEvent(kind="reasoning", text=turn.reasoning, reasoning_tokens=turn.reasoning_tokens)
        if turn.text:
            yield StreamEvent(kind="text", text=turn.text)
        for call in turn.tool_calls:
            yield StreamEvent(kind="tool_call", tool_call=call)
        yield StreamEvent(
            kind="usage",
            input_tokens=turn.input_tokens,
            output_tokens=turn.output_tokens,
            cached_input_tokens=turn.cached_input_tokens,
            reasoning_tokens=turn.reasoning_tokens,
        )
        yield StreamEvent(kind="done")

    async def validate_key(self, api_key: str, base_url: str | None = None) -> bool:
        return api_key.startswith("sk-") or api_key == "valid"


class OpenAIProvider:
    async def stream(
        self,
        *,
        model: str,
        messages: list[dict[str, Any]],
        api_key: str,
        base_url: str | None = None,
    ) -> AsyncIterator[StreamEvent]:
        url = (base_url or "https://api.openai.com/v1").rstrip("/") + "/chat/completions"
        async for event in _sse_chat(url, model, messages, api_key, "openai"):
            yield event

    async def validate_key(self, api_key: str, base_url: str | None = None) -> bool:
        url = (base_url or "https://api.openai.com/v1").rstrip("/") + "/models"
        return await _probe(url, {"Authorization": f"Bearer {api_key}"})


class AnthropicProvider:
    async def stream(
        self,
        *,
        model: str,
        messages: list[dict[str, Any]],
        api_key: str,
        base_url: str | None = None,
    ) -> AsyncIterator[StreamEvent]:
        url = (base_url or "https://api.anthropic.com/v1").rstrip("/") + "/messages"
        payload = {
            "model": model,
            "max_tokens": 1024,
            "stream": True,
            "messages": [m for m in messages if m.get("role") != "system"],
        }
        headers = {
            "x-api-key": api_key,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json",
        }
        async with httpx.AsyncClient(timeout=60) as client:
            response = await client.post(url, json=payload, headers=headers)
            if response.status_code >= 400:
                failure = normalize_provider_error(response.status_code, response.text)
                yield StreamEvent(kind="error", error_code=failure.code, text=failure.detail)
                return
            yield StreamEvent(kind="text", text=response.text)
            yield StreamEvent(kind="done")

    async def validate_key(self, api_key: str, base_url: str | None = None) -> bool:
        url = (base_url or "https://api.anthropic.com/v1").rstrip("/") + "/messages"
        headers = {"x-api-key": api_key, "anthropic-version": "2023-06-01"}
        payload = {
            "model": "claude-3-5-haiku-latest",
            "max_tokens": 1,
            "messages": [{"role": "user", "content": "ping"}],
        }
        async with httpx.AsyncClient(timeout=20) as client:
            response = await client.post(url, json=payload, headers=headers)
        return response.status_code < 400


class LiteLLMProvider:
    def __init__(self, proxy_url: str = "http://localhost:4000") -> None:
        self.proxy_url = proxy_url
        self._openai = OpenAIProvider()

    async def stream(
        self,
        *,
        model: str,
        messages: list[dict[str, Any]],
        api_key: str,
        base_url: str | None = None,
    ) -> AsyncIterator[StreamEvent]:
        async for event in self._openai.stream(
            model=model,
            messages=messages,
            api_key=api_key,
            base_url=base_url or self.proxy_url,
        ):
            yield event

    async def validate_key(self, api_key: str, base_url: str | None = None) -> bool:
        return await self._openai.validate_key(api_key, base_url or self.proxy_url)


async def _probe(url: str, headers: dict[str, str]) -> bool:
    async with httpx.AsyncClient(timeout=20) as client:
        response = await client.get(url, headers=headers)
    return response.status_code < 400


async def _sse_chat(
    url: str,
    model: str,
    messages: list[dict[str, Any]],
    api_key: str,
    style: str,
) -> AsyncIterator[StreamEvent]:
    payload = {"model": model, "messages": messages, "stream": True}
    headers = {"Authorization": f"Bearer {api_key}", "content-type": "application/json"}
    async with httpx.AsyncClient(timeout=60) as client:
        response = await client.post(url, json=payload, headers=headers)
        if response.status_code >= 400:
            failure = normalize_provider_error(
                response.status_code,
                response.text,
                response.headers.get("retry-after"),
            )
            yield StreamEvent(kind="error", error_code=failure.code, text=failure.detail)
            return
        yield StreamEvent(kind="text", text=response.text)
        yield StreamEvent(kind="done")


def tool_call(name: str, arguments: dict[str, Any], call_id: str = "call_1") -> ToolCall:
    return ToolCall(id=call_id, name=name, arguments=arguments)
