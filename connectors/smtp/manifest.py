from younique_sdk import ConnectorManifest, PermissionBundle, tool

MANIFEST = ConnectorManifest(
    key="smtp",
    display_name="Email (SMTP)",
    description="Send email with an app password. Cannot read a mailbox.",
    auth="smtp",
    limitations=["Send-only. There is no inbox, search, or read tool."],
    approval_status="not_applicable",
    bundles=[
        PermissionBundle(
            key="send",
            display_name="Send email",
            description="Send email as you. Cannot read your mailbox.",
            scopes=[],
            tools=["smtp.send"],
            risk="high",
            produces_untrusted_content=False,
        )
    ],
)


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


@tool(
    key="smtp.send",
    title="Send email",
    description="Send an email through the connected SMTP account.",
    risk="high",
    bundle="send",
)
async def send_email(ctx, arguments: dict[str, object]) -> dict[str, object]:
    recipients = arguments.get("to")
    if isinstance(recipients, str):
        recipients = [recipients]
    if not isinstance(recipients, list) or len(recipients) > 25:
        from younique_sdk import ConnectorError

        raise ConnectorError("validation_failed", "At most 25 recipients are allowed.")
    attachments = arguments.get("attachments") or []
    if not isinstance(attachments, list) or len(attachments) > 10:
        from younique_sdk import ConnectorError

        raise ConnectorError("validation_failed", "At most 10 attachments are allowed.")
    await ctx.send_smtp(
        host=str(ctx.secrets.get("host") or ""),
        port=int(str(ctx.secrets.get("port") or "587")),
        username=str(ctx.secrets.get("username") or ""),
        password=str(ctx.secrets.get("password") or ""),
        sender=str(ctx.secrets.get("sender") or ctx.secrets.get("username") or ""),
        recipients=[str(item) for item in recipients],
        subject=str(arguments.get("subject") or ""),
        body=str(arguments.get("body") or ""),
        attachments=[item for item in attachments if isinstance(item, dict)],
    )
    return {"sent": True, "recipients": recipients}


TOOLS = [send_email]
