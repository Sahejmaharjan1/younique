from younique_sdk import ConnectorManifest, PermissionBundle, tool

MANIFEST = ConnectorManifest(
    key="google_drive",
    display_name="Google Drive",
    description="Read files the user opens or creates with this app.",
    auth="oauth",
    limitations=[
        "Uses the non-restricted drive.file scope, so only files this app created or the user picked are visible.",
    ],
    approval_status="not_restricted",
    bundles=[
        PermissionBundle(
            key="read",
            display_name="Read files",
            description="Read file contents the user has granted. Contents are untrusted.",
            scopes=["https://www.googleapis.com/auth/drive.file"],
            tools=["drive.read"],
            risk="low",
            produces_untrusted_content=True,
        )
    ],
)


@tool(key="drive.read", title="Read Drive file", description="Read a granted Drive file.", risk="low", bundle="read")
async def read_file(ctx, arguments: dict[str, object]) -> dict[str, object]:
    ref = str(arguments.get("file_id") or "")
    ctx.require_grant(ref, "read")
    response = await ctx.http.request(
        "GET",
        f"https://www.googleapis.com/drive/v3/files/{ref}",
        headers={"Authorization": f"Bearer {ctx.secrets.get('access_token', '')}"},
    )
    return {"body": response.text, "trust": "untrusted"}


TOOLS = [read_file]
