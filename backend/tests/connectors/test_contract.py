from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import httpx
import pytest
from younique_sdk import ConnectorError, ToolContext

from younique.connectors.registry import CONNECTOR_KEYS, load_module

CASSETTES = Path(__file__).parent / "cassettes"


def _cassette(name: str) -> dict[str, Any]:
    loaded = json.loads((CASSETTES / name).read_text())
    if not isinstance(loaded, dict):
        raise AssertionError(name)
    return loaded


def _transport(cassette: dict[str, Any]) -> httpx.MockTransport:
    expected = cassette["request"]
    response = cassette["response"]

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.method == expected["method"]
        assert str(request.url) == expected["url"]
        headers = response.get("headers") or {}
        if "json" in response:
            return httpx.Response(int(response["status"]), json=response["json"], headers=headers)
        return httpx.Response(
            int(response["status"]), text=str(response.get("text") or ""), headers=headers
        )

    return httpx.MockTransport(handler)


def _gmail(
    transport: httpx.MockTransport, grants: list[dict[str, Any]]
) -> tuple[ToolContext, httpx.AsyncClient]:
    client = httpx.AsyncClient(transport=transport)
    ctx = ToolContext(
        workspace_id="w",
        user_id="u",
        connection_id="c",
        grants=grants,
        secrets={"access_token": "token"},
        allowlist=["gmail.googleapis.com"],
        resolver=lambda host: ["8.8.8.8"],
        http_client=client,
    )
    return ctx, client


def test_manifests_reference_real_tools() -> None:
    for key in CONNECTOR_KEYS:
        module = load_module(key)
        tools = {getattr(tool, "__tool_key__", "") for tool in module.TOOLS}
        assert module.MANIFEST.key == key
        for bundle in module.MANIFEST.bundles:
            assert bundle.risk in {"low", "medium", "high"}
            assert isinstance(bundle.produces_untrusted_content, bool)
            assert bundle.tools
            for tool_key in bundle.tools:
                assert tool_key in tools


@pytest.mark.asyncio
async def test_gmail_send_replays_cassette() -> None:
    module = load_module("gmail")
    ctx, client = _gmail(
        _transport(_cassette("gmail_send_200.json")),
        [{"resource_ref": "me", "allowed_actions": ["send"]}],
    )
    async with client:
        sent = await module.send_email(ctx, {"mailbox": "me", "raw": "aGVsbG8="})
    assert sent["sent"] is True
    assert sent["id"] == "msg-1"


@pytest.mark.asyncio
async def test_gmail_read_replays_cassette() -> None:
    module = load_module("gmail")
    ctx, client = _gmail(
        _transport(_cassette("gmail_get_200.json")),
        [{"resource_ref": "me", "allowed_actions": ["read"]}],
    )
    async with client:
        message = await module.get_message(ctx, {"mailbox": "me", "id": "18"})
    assert message["trust"] == "untrusted"
    assert message["body"]["snippet"] == "Hello"


@pytest.mark.asyncio
async def test_gmail_rate_limit_is_retryable() -> None:
    module = load_module("gmail")
    ctx, client = _gmail(
        _transport(_cassette("gmail_send_429.json")),
        [{"resource_ref": "me", "allowed_actions": ["send"]}],
    )
    async with client:
        with pytest.raises(ConnectorError) as caught:
            await module.send_email(ctx, {"mailbox": "me", "raw": "aGVsbG8="})
    assert caught.value.code == "connector_rate_limited"
    assert caught.value.retryable is True
    assert "3" in caught.value.detail


@pytest.mark.asyncio
async def test_gmail_auth_and_malformed_errors() -> None:
    module = load_module("gmail")
    denied, denied_client = _gmail(
        _transport(_cassette("gmail_get_401.json")),
        [{"resource_ref": "me", "allowed_actions": ["read"]}],
    )
    async with denied_client:
        with pytest.raises(ConnectorError) as auth:
            await module.get_message(denied, {"mailbox": "me", "id": "missing"})
    assert auth.value.code == "connection_needs_reauth"
    broken, broken_client = _gmail(
        _transport(_cassette("gmail_get_malformed.json")),
        [{"resource_ref": "me", "allowed_actions": ["read"]}],
    )
    async with broken_client:
        with pytest.raises(ConnectorError) as malformed:
            await module.get_message(broken, {"mailbox": "me", "id": "bad"})
    assert malformed.value.code == "connector_unavailable"


@pytest.mark.asyncio
async def test_grant_is_enforced_before_http() -> None:
    module = load_module("gmail")

    def explode(request: httpx.Request) -> httpx.Response:
        raise AssertionError(f"unexpected call {request.url}")

    ctx, client = _gmail(httpx.MockTransport(explode), [])
    async with client:
        with pytest.raises(ConnectorError) as caught:
            await module.get_message(ctx, {"id": "1", "mailbox": "me"})
    assert caught.value.code == "connector_resource_not_granted"


@pytest.mark.asyncio
async def test_smtp_grant_and_validation_skip_transport() -> None:
    module = load_module("smtp")
    calls: list[str] = []

    async def capture(**kwargs: object) -> None:
        calls.append("sent")

    denied = ToolContext(
        workspace_id="w",
        user_id="u",
        connection_id="c",
        grants=[],
        secrets={"host": "smtp.example", "username": "a", "password": "b"},
        smtp_send=capture,
    )
    with pytest.raises(ConnectorError) as missing:
        await module.send_email(denied, {"to": "ops@example.com", "subject": "Hi", "body": "Body"})
    assert missing.value.code == "connector_resource_not_granted"
    allowed = ToolContext(
        workspace_id="w",
        user_id="u",
        connection_id="c",
        grants=[{"resource_ref": "smtp", "allowed_actions": ["send"]}],
        secrets={"host": "smtp.example", "port": "587", "username": "a", "password": "b"},
        smtp_send=capture,
    )
    with pytest.raises(ConnectorError) as invalid:
        await module.send_email(
            allowed,
            {
                "to": [f"u{index}@example.com" for index in range(26)],
                "subject": "Hi",
                "body": "Body",
            },
        )
    assert invalid.value.code == "validation_failed"
    assert calls == []
    await module.send_email(allowed, {"to": "ops@example.com", "subject": "Hi", "body": "Body"})
    assert calls == ["sent"]
