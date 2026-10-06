from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from younique_sdk.http import Resolver, SafeHttp


@dataclass
class ToolContext:
    workspace_id: str
    user_id: str
    connection_id: str | None
    grants: list[dict[str, Any]] = field(default_factory=list)
    secrets: dict[str, str] = field(default_factory=dict)
    allowlist: list[str] = field(default_factory=list)
    resolver: Resolver | None = None
    http_client: Any = None
    smtp_send: Callable[..., Any] | None = None
    _http_calls: list[str] = field(default_factory=list)

    @property
    def http(self) -> SafeHttp:
        return SafeHttp(
            allowlist=self.allowlist,
            resolver=self.resolver,
            client=self.http_client,
        )

    def require_grant(self, resource_ref: str, action: str) -> None:
        from younique_sdk.errors import ConnectorError

        for grant in self.grants:
            if grant.get("resource_ref") == resource_ref and action in grant.get("allowed_actions", []):
                return
        raise ConnectorError(
            "connector_resource_not_granted",
            f"Resource {resource_ref} is not granted for {action}",
        )

    async def send_smtp(
        self,
        *,
        host: str,
        port: int,
        username: str,
        password: str,
        sender: str,
        recipients: list[str],
        subject: str,
        body: str,
        attachments: list[dict[str, str]] | None = None,
    ) -> None:
        if self.smtp_send is None:
            from younique_sdk.errors import ConnectorError

            raise ConnectorError("connector_unavailable", "SMTP transport is not configured")
        await self.smtp_send(
            host=host,
            port=port,
            username=username,
            password=password,
            sender=sender,
            recipients=recipients,
            subject=subject,
            body=body,
            attachments=attachments or [],
        )
