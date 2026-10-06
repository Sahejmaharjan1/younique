from younique_sdk import ConnectorError, ConnectorManifest, PermissionBundle, tool

MANIFEST = ConnectorManifest(
    key="http",
    display_name="HTTP",
    description="Call HTTPS endpoints on an explicit host allowlist.",
    auth="none",
    limitations=[
        "No host is allowed until you add it.",
        "Private, loopback, and link-local addresses are refused, including the cloud metadata endpoint.",
        "POST, PUT, and PATCH in a tainted run require approval.",
    ],
    bundles=[
        PermissionBundle(
            key="request",
            display_name="HTTP request",
            description="Send a request to an allowlisted host.",
            scopes=[],
            tools=["http.request"],
            risk="high",
            produces_untrusted_content=True,
        )
    ],
)


def summarize_for_approval(arguments: dict[str, object], flagged: list[str]) -> dict[str, object]:
    return {
        "headline": f"{arguments.get('method', 'GET')} {arguments.get('url')}",
        "details": [{"label": "URL", "value": arguments.get("url"), "flagged": "url" in flagged}],
        "body_preview": str(arguments.get("body") or "")[:280],
        "irreversible": str(arguments.get("method") or "GET").upper() != "GET",
        "flagged_args": flagged,
    }


@tool(key="http.request", title="HTTP request", description="Request an allowlisted URL.", risk="high", bundle="request")
async def request_url(ctx, arguments: dict[str, object]) -> dict[str, object]:
    url = str(arguments.get("url") or "")
    host = str(arguments.get("host") or "")
    if host and host not in ctx.allowlist:
        raise ConnectorError("connector_permission_denied", "Host is not allowlisted.")
    response = await ctx.http.request(
        str(arguments.get("method") or "GET"),
        url,
        json=arguments.get("json") if isinstance(arguments.get("json"), dict) else None,
    )
    return {"status": response.status_code, "body": response.text, "trust": "untrusted"}


TOOLS = [request_url]
