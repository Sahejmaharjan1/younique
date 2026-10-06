from __future__ import annotations

import importlib.util
from pathlib import Path
from types import ModuleType

from younique_sdk import ConnectorManifest, PermissionBundle

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


def _load(filename: str) -> ModuleType:
    path = Path(__file__).resolve().parent / "tools" / filename
    spec = importlib.util.spec_from_file_location(f"younique_connector_gmail_{path.stem}", path)
    if spec is None or spec.loader is None:
        raise FileNotFoundError(path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


_api = _load("api.py")
send_email = _api.send_email
get_message = _api.get_message
summarize_for_approval = _api.summarize_for_approval
TOOLS = [send_email, get_message]
