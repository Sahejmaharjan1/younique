from uuid import UUID

import yaml

from younique.authz.policy import decide
from younique.authz.principal import Principal, ResourceView
from younique.core.security import session_cookie

HOME = UUID("00000000-0000-7000-8000-0000000000aa")
OTHER = UUID("00000000-0000-7000-8000-0000000000bb")
SELF = UUID("00000000-0000-7000-8000-000000000001")
ALIEN = UUID("00000000-0000-7000-8000-000000000002")


def _principal(name: str) -> Principal:
    base = dict(user_id=SELF, workspace_id=HOME, workspace_role="member", kind="user")
    table: dict[str, dict[str, object]] = {
        "owner": {**base, "workspace_role": "owner"},
        "admin": {**base, "workspace_role": "admin"},
        "member": base,
        "guest": {**base, "workspace_role": "guest"},
        "non_member": {
            "kind": "user",
            "user_id": ALIEN,
            "workspace_id": None,
            "workspace_role": None,
        },
        "share_link_viewer": {"kind": "share_link", "share_role": "viewer", "workspace_id": HOME},
        "share_link_commenter": {
            "kind": "share_link",
            "share_role": "commenter",
            "workspace_id": HOME,
        },
        "anonymous": {"kind": "anonymous"},
        "pat_limited_scope": {**base, "kind": "pat", "scopes": frozenset({"chat.read"})},
        "mcp_token": {**base, "kind": "mcp_client", "scopes": frozenset({"tools.invoke"})},
        "agent_acting_for_member": {
            **base,
            "kind": "agent",
            "tool_allowlist": frozenset({"smtp.send"}),
        },
        "archived_member": {**base, "archived_membership": True},
        "revoked_session": {**base, "revoked": True},
    }
    return Principal(**table[name])  # type: ignore[arg-type]


def _resource(name: str) -> ResourceView:
    chat = dict(type="chat", id=SELF, workspace_id=HOME, owner_user_id=SELF)
    table: dict[str, dict[str, object]] = {
        "own_chat": chat,
        "other_member_chat": {**chat, "owner_user_id": ALIEN},
        "other_workspace_chat": {**chat, "workspace_id": OTHER, "owner_user_id": ALIEN},
        "shared_chat": {
            **chat,
            "owner_user_id": ALIEN,
            "link_visible": True,
            "grant_role": "viewer",
        },
        "archived_chat": {**chat, "archived": True},
        "artifact_clean": {
            "type": "artifact",
            "id": SELF,
            "workspace_id": HOME,
            "owner_user_id": SELF,
            "status": "clean",
        },
        "artifact_infected": {
            "type": "artifact",
            "id": SELF,
            "workspace_id": HOME,
            "owner_user_id": SELF,
            "status": "infected",
        },
        "agent": {"type": "agent", "id": SELF, "workspace_id": HOME, "owner_user_id": SELF},
        "pipeline": {"type": "pipeline", "id": SELF, "workspace_id": HOME, "owner_user_id": SELF},
        "personal_memory_set": {
            "type": "memory_set",
            "id": SELF,
            "workspace_id": HOME,
            "owner_user_id": SELF,
            "private": True,
        },
        "workspace_memory_set": {
            "type": "memory_set",
            "id": SELF,
            "workspace_id": HOME,
            "owner_user_id": None,
        },
        "connection": {
            "type": "connection",
            "id": SELF,
            "workspace_id": HOME,
            "owner_user_id": SELF,
            "private": True,
        },
        "provider_key": {
            "type": "provider_key",
            "id": SELF,
            "workspace_id": HOME,
            "owner_user_id": SELF,
            "private": True,
        },
        "audit_log": {"type": "audit_log", "id": SELF, "workspace_id": HOME, "owner_user_id": None},
        "budget": {"type": "budget", "id": SELF, "workspace_id": HOME, "owner_user_id": None},
        "mcp_token": {
            "type": "mcp_token",
            "id": SELF,
            "workspace_id": HOME,
            "owner_user_id": SELF,
            "private": True,
        },
        "tool": {
            "type": "tool",
            "id": None,
            "workspace_id": HOME,
            "tool_key": "smtp.send",
            "status": "smtp.send",
        },
    }
    return ResourceView(**table[name])  # type: ignore[arg-type]


def test_cross_workspace_is_404() -> None:
    decision = decide(_principal("owner"), "read", _resource("other_workspace_chat"))
    assert decision.status == 404
    assert decision.code == "not_found"


def test_share_link_cannot_use_tools_or_secrets() -> None:
    principal = _principal("share_link_viewer")
    for action in ("execute_tool", "read_secret", "rotate_secret", "decide_approval"):
        decision = decide(principal, action, _resource("shared_chat"))
        assert decision.status == 403
        assert decision.code == "permission_denied"


def test_guest_cannot_run() -> None:
    decision = decide(_principal("guest"), "run", _resource("own_chat"))
    assert decision.status == 403


def test_agent_allowlist_intersection() -> None:
    allowed = decide(_principal("agent_acting_for_member"), "execute_tool", _resource("tool"))
    assert allowed.allowed
    blocked = _resource("tool")
    denied = decide(
        Principal(
            kind="agent",
            user_id=SELF,
            workspace_id=HOME,
            workspace_role="member",
            tool_allowlist=frozenset(),
        ),
        "execute_tool",
        blocked,
    )
    assert not denied.allowed


def test_archived_visible_to_reader_is_410() -> None:
    decision = decide(_principal("owner"), "read", _resource("archived_chat"))
    assert decision.status == 410
    hidden = decide(_principal("non_member"), "read", _resource("archived_chat"))
    assert hidden.status == 404


def test_secrets_are_never_readable() -> None:
    decision = decide(_principal("owner"), "read_secret", _resource("provider_key"))
    assert decision.status == 403


def test_cookie_is_host_prefixed() -> None:
    header = session_cookie("abc", secure=True)
    assert header.startswith("__Host-session=abc")
    assert "HttpOnly" in header
    assert "Secure" in header
    assert "Path=/" in header
    assert "Domain=" not in header


def test_matrix_fixture_covers_every_cell() -> None:
    document = yaml.safe_load(
        (__import__("pathlib").Path(__file__).parent / "expectations.yaml").read_text()
    )
    principals = document["principals"]
    resources = document["resources"]
    actions = document["actions"]
    cells = document["cells"]
    assert len(cells) == len(principals) * len(resources) * len(actions)
    for principal_name in principals:
        for resource_name in resources:
            for action in actions:
                key = f"{principal_name}|{resource_name}|{action}"
                expected = cells[key]
                decision = decide(_principal(principal_name), action, _resource(resource_name))
                assert decision.status == expected["status"], key
                assert decision.code == expected["code"], key
