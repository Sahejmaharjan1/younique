from __future__ import annotations

from typing import Any

from younique_sdk import ConnectorError, tool


def summarize_for_approval(arguments: dict[str, object], flagged: list[str]) -> dict[str, object]:
    return {
        "headline": f"Send Gmail to {arguments.get('to')}",
        "details": [{"label": "To", "value": arguments.get("to"), "flagged": "to" in flagged}],
        "body_preview": str(arguments.get("body") or "")[:280],
        "irreversible": True,
        "flagged_args": flagged,
    }


def raise_for_provider(response: Any) -> None:
    status = int(getattr(response, "status_code", 0))
    headers = getattr(response, "headers", {})
    retry_after = ""
    if hasattr(headers, "get"):
        retry_after = str(headers.get("retry-after") or "")
    if status < 400:
        return
    if status == 401:
        raise ConnectorError("connection_needs_reauth", "Gmail rejected the access token.")
    if status == 403:
        raise ConnectorError("connector_permission_denied", "Gmail denied this request.")
    if status == 404:
        raise ConnectorError("connector_unavailable", "Gmail could not find that message.")
    if status == 429:
        detail = "Gmail rate limited the request."
        if retry_after:
            detail = f"{detail} Retry after {retry_after} seconds."
        raise ConnectorError("connector_rate_limited", detail, retryable=True)
    if status >= 500:
        raise ConnectorError("connector_unavailable", f"Gmail returned {status}.", retryable=True)
    raise ConnectorError("connector_unavailable", f"Gmail returned {status}.")


def read_json(response: Any) -> dict[str, Any]:
    try:
        payload = response.json()
    except Exception as exc:
        raise ConnectorError("connector_unavailable", "Gmail returned a malformed body.") from exc
    if not isinstance(payload, dict):
        raise ConnectorError("connector_unavailable", "Gmail returned a malformed body.")
    return payload


def _auth(ctx: Any) -> dict[str, str]:
    return {"Authorization": f"Bearer {ctx.secrets.get('access_token', '')}"}


@tool(key="gmail.send_email", title="Send Gmail", description="Send a Gmail message.", risk="high", bundle="send")
async def send_email(ctx: Any, arguments: dict[str, object]) -> dict[str, object]:
    ctx.require_grant(str(arguments.get("mailbox") or "me"), "send")
    response = await ctx.http.request(
        "POST",
        "https://gmail.googleapis.com/gmail/v1/users/me/messages/send",
        headers=_auth(ctx),
        json={"raw": str(arguments.get("raw") or "")},
    )
    raise_for_provider(response)
    payload = read_json(response)
    return {"sent": True, "id": payload.get("id")}


@tool(key="gmail.get_message", title="Read Gmail", description="Read one Gmail message.", risk="low", bundle="read")
async def get_message(ctx: Any, arguments: dict[str, object]) -> dict[str, object]:
    ctx.require_grant(str(arguments.get("mailbox") or "me"), "read")
    response = await ctx.http.request(
        "GET",
        f"https://gmail.googleapis.com/gmail/v1/users/me/messages/{arguments.get('id')}",
        headers=_auth(ctx),
    )
    raise_for_provider(response)
    payload = read_json(response)
    return {"body": payload, "trust": "untrusted"}
