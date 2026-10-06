from younique_sdk import ConnectorManifest, PermissionBundle, tool

MANIFEST = ConnectorManifest(
    key="gmail",
    display_name="Gmail",
    description="Send and read Gmail with a workspace-supplied OAuth client.",
    auth="oauth",
    limitations=[
        "Hosted Gmail requires Google OAuth verification and CASA.",
        "Until verification completes, connect with your own OAuth client.",
        "A send-only connection does not include read tools.",
    ],
    approval_status="verification_required",
    bundles=[
        PermissionBundle(
            key="send",
            display_name="Send email",
            description="Send email as you. Cannot read your mailbox.",
            scopes=["https://www.googleapis.com/auth/gmail.send"],
            tools=["gmail.send_email"],
            risk="high",
            produces_untrusted_content=False,
        ),
        PermissionBundle(
            key="read",
            display_name="Read email",
            description="Read messages you select. Content is untrusted.",
            scopes=["https://www.googleapis.com/auth/gmail.readonly"],
            tools=["gmail.get_message"],
            risk="low",
            produces_untrusted_content=True,
        ),
    ],
)


def summarize_for_approval(arguments: dict[str, object], flagged: list[str]) -> dict[str, object]:
    return {
        "headline": f"Send Gmail to {arguments.get('to')}",
        "details": [{"label": "To", "value": arguments.get("to"), "flagged": "to" in flagged}],
        "body_preview": str(arguments.get("body") or "")[:280],
        "irreversible": True,
        "flagged_args": flagged,
    }


@tool(key="gmail.send_email", title="Send Gmail", description="Send a Gmail message.", risk="high", bundle="send")
async def send_email(ctx, arguments: dict[str, object]) -> dict[str, object]:
    ctx.require_grant(str(arguments.get("mailbox") or "me"), "send")
    await ctx.http.request(
        "POST",
        "https://gmail.googleapis.com/gmail/v1/users/me/messages/send",
        headers={"Authorization": f"Bearer {ctx.secrets.get('access_token', '')}"},
        json={"raw": str(arguments.get("raw") or "")},
    )
    return {"sent": True}


@tool(key="gmail.get_message", title="Read Gmail", description="Read one Gmail message.", risk="low", bundle="read")
async def get_message(ctx, arguments: dict[str, object]) -> dict[str, object]:
    ctx.require_grant(str(arguments.get("mailbox") or "me"), "read")
    response = await ctx.http.request(
        "GET",
        f"https://gmail.googleapis.com/gmail/v1/users/me/messages/{arguments.get('id')}",
        headers={"Authorization": f"Bearer {ctx.secrets.get('access_token', '')}"},
    )
    return {"body": response.text, "trust": "untrusted"}


TOOLS = [send_email, get_message]
