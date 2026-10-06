from younique_sdk import ConnectorManifest, PermissionBundle, tool

MANIFEST = ConnectorManifest(
    key="google_sheets",
    display_name="Google Sheets",
    description="Read and write spreadsheets the user selects.",
    auth="oauth",
    limitations=["Only spreadsheets granted on the connection can be used."],
    bundles=[
        PermissionBundle(
            key="read",
            display_name="Read sheets",
            description="Read cells from granted spreadsheets.",
            scopes=["https://www.googleapis.com/auth/spreadsheets.readonly"],
            tools=["sheets.read"],
            risk="low",
            produces_untrusted_content=True,
        ),
        PermissionBundle(
            key="write",
            display_name="Write sheets",
            description="Update cells in granted spreadsheets.",
            scopes=["https://www.googleapis.com/auth/spreadsheets"],
            tools=["sheets.write"],
            risk="medium",
            produces_untrusted_content=False,
        ),
    ],
)


@tool(key="sheets.read", title="Read sheet", description="Read a range.", risk="low", bundle="read")
async def read_sheet(ctx, arguments: dict[str, object]) -> dict[str, object]:
    ref = str(arguments.get("spreadsheet_id") or "")
    ctx.require_grant(ref, "read")
    response = await ctx.http.request(
        "GET",
        f"https://sheets.googleapis.com/v4/spreadsheets/{ref}/values/{arguments.get('range')}",
        headers={"Authorization": f"Bearer {ctx.secrets.get('access_token', '')}"},
    )
    return {"values": response.text, "trust": "untrusted"}


@tool(key="sheets.write", title="Write sheet", description="Write a range.", risk="medium", bundle="write")
async def write_sheet(ctx, arguments: dict[str, object]) -> dict[str, object]:
    ref = str(arguments.get("spreadsheet_id") or "")
    ctx.require_grant(ref, "write")
    await ctx.http.request(
        "PUT",
        f"https://sheets.googleapis.com/v4/spreadsheets/{ref}/values/{arguments.get('range')}",
        headers={"Authorization": f"Bearer {ctx.secrets.get('access_token', '')}"},
        json={"values": arguments.get("values") or []},
    )
    return {"updated": True}


def summarize_for_approval(arguments: dict[str, object], flagged: list[str]) -> dict[str, object]:
    return {
        "headline": "Update a spreadsheet",
        "details": [{"label": "Range", "value": arguments.get("range"), "flagged": "range" in flagged}],
        "body_preview": "",
        "irreversible": False,
        "flagged_args": flagged,
    }


TOOLS = [read_sheet, write_sheet]
