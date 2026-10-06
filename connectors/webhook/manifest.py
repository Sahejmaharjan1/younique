import hashlib
import hmac
import time

from younique_sdk import ConnectorError, ConnectorManifest, PermissionBundle, tool

MANIFEST = ConnectorManifest(
    key="webhook",
    display_name="Webhook",
    description="Receive signed webhooks and reject replays.",
    auth="webhook",
    limitations=["Inbound only. Unsigned or replayed deliveries are rejected."],
    bundles=[
        PermissionBundle(
            key="receive",
            display_name="Receive webhooks",
            description="Accept HMAC-signed webhook deliveries.",
            scopes=[],
            tools=["webhook.receive"],
            risk="low",
            produces_untrusted_content=True,
        )
    ],
)


def verify_delivery(
    *,
    secret: str,
    body: bytes,
    signature: str,
    timestamp: int,
    nonce: str,
    seen: set[str],
    now: int | None = None,
) -> None:
    current = int(time.time()) if now is None else now
    if abs(current - timestamp) > 300:
        raise ConnectorError("connector_permission_denied", "Webhook timestamp is outside the window.")
    if nonce in seen:
        raise ConnectorError("connector_permission_denied", "Webhook nonce was already used.")
    signed = f"{timestamp}.{nonce}.".encode() + body
    expected = hmac.new(secret.encode(), signed, hashlib.sha256).hexdigest()
    if not hmac.compare_digest(expected, signature):
        raise ConnectorError("connector_permission_denied", "Webhook signature is invalid.")


@tool(key="webhook.receive", title="Receive webhook", description="Accept a signed webhook.", risk="low", bundle="receive")
async def receive(ctx, arguments: dict[str, object]) -> dict[str, object]:
    return {"accepted": True, "trust": "untrusted", "body": arguments.get("body")}


TOOLS = [receive]
