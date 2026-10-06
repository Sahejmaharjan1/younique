from __future__ import annotations

from typing import Any

from younique_sdk import ConnectorError, tool


def summarize_for_approval(arguments: dict[str, object], flagged: list[str]) -> dict[str, object]:
    return {
        "headline": f"Send email to {arguments.get('to')}",
        "details": [
            {"label": "To", "value": arguments.get("to"), "flagged": "to" in flagged},
            {"label": "Subject", "value": arguments.get("subject"), "flagged": "subject" in flagged},
        ],
        "body_preview": str(arguments.get("body") or "")[:280],
        "irreversible": True,
        "flagged_args": flagged,
    }


def _recipients(arguments: dict[str, object]) -> list[str]:
    recipients = arguments.get("to")
    if isinstance(recipients, str):
        recipients = [recipients]
    if not isinstance(recipients, list) or not recipients or len(recipients) > 25:
        raise ConnectorError("validation_failed", "At most 25 recipients are allowed.")
    return [str(item) for item in recipients]


def _attachments(arguments: dict[str, object]) -> list[dict[str, str]]:
    attachments = arguments.get("attachments") or []
    if not isinstance(attachments, list) or len(attachments) > 10:
        raise ConnectorError("validation_failed", "At most 10 attachments are allowed.")
    return [item for item in attachments if isinstance(item, dict)]


@tool(
    key="smtp.send",
    title="Send email",
    description="Send an email through the connected SMTP account.",
    risk="high",
    bundle="send",
)
async def send_email(ctx: Any, arguments: dict[str, object]) -> dict[str, object]:
    ctx.require_grant("smtp", "send")
    recipients = _recipients(arguments)
    attachments = _attachments(arguments)
    await ctx.send_smtp(
        host=str(ctx.secrets.get("host") or ""),
        port=int(str(ctx.secrets.get("port") or "587")),
        username=str(ctx.secrets.get("username") or ""),
        password=str(ctx.secrets.get("password") or ""),
        sender=str(ctx.secrets.get("sender") or ctx.secrets.get("username") or ""),
        recipients=recipients,
        subject=str(arguments.get("subject") or ""),
        body=str(arguments.get("body") or ""),
        attachments=attachments,
    )
    return {"sent": True, "recipients": recipients}
