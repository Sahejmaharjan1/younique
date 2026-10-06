from __future__ import annotations

import importlib.util
from pathlib import Path
from types import ModuleType

from younique_sdk import ConnectorManifest, PermissionBundle

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


def _load(filename: str) -> ModuleType:
    path = Path(__file__).resolve().parent / "tools" / filename
    spec = importlib.util.spec_from_file_location(f"younique_connector_smtp_{path.stem}", path)
    if spec is None or spec.loader is None:
        raise FileNotFoundError(path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


_send = _load("send_email.py")
send_email = _send.send_email
summarize_for_approval = _send.summarize_for_approval
TOOLS = [send_email]
