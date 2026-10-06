from __future__ import annotations

from younique.authz.principal import Decision, Principal, ResourceView

_RANK = {"viewer": 1, "commenter": 2, "editor": 3, "owner": 4}
_SECRET_ACTIONS = {"read_secret", "rotate_secret"}
_WRITE_ACTIONS = {"update", "delete", "share", "run", "create", "execute_tool", "decide_approval"}


def _ok() -> Decision:
    return Decision(True, 200, "ok")


def _deny(status: int, code: str) -> Decision:
    return Decision(False, status, code)


def _role_rank(role: str | None) -> int:
    if role is None:
        return 0
    return _RANK.get(role, 0)


def _workspace_ceiling(principal: Principal, resource: ResourceView) -> str | None:
    if principal.workspace_id is None or resource.workspace_id is None:
        return None
    if principal.workspace_id != resource.workspace_id:
        return None
    if principal.workspace_role in {"owner", "admin"} and not resource.private:
        return "editor"
    if (
        principal.user_id is not None
        and resource.owner_user_id == principal.user_id
        and principal.workspace_role in {"owner", "admin", "member"}
    ):
        return "owner"
    return None


def decide(principal: Principal, action: str, resource: ResourceView) -> Decision:
    if principal.revoked or principal.kind == "anonymous":
        code = "session_revoked" if principal.revoked else "unauthenticated"
        return _deny(401, code)
    if principal.archived_membership:
        if (
            resource.workspace_id
            and principal.workspace_id
            and resource.workspace_id != principal.workspace_id
        ):
            return _deny(404, "not_found")
        return _deny(403, "permission_denied")
    if (
        resource.workspace_id
        and principal.workspace_id
        and resource.workspace_id != principal.workspace_id
    ):
        if principal.kind != "share_link":
            return _deny(404, "not_found")
    if principal.kind == "share_link" and (
        action.startswith("tool.")
        or action in _SECRET_ACTIONS
        or action in {"execute_tool", "decide_approval", "run", "rotate_secret", "create"}
    ):
        return _deny(403, "permission_denied")
    if principal.kind in {"pat", "mcp_client"} and action in _SECRET_ACTIONS:
        return _deny(403, "permission_denied")
    if principal.kind in {"pat", "mcp_client", "agent"} and action == "decide_approval":
        return _deny(403, "permission_denied")
    if action in _SECRET_ACTIONS and resource.type in {"connection", "provider_key"}:
        return _deny(403, "permission_denied")
    if resource.archived:
        if _could_read(principal, resource):
            return _deny(410, "archived")
        return _deny(404, "not_found")
    if (
        resource.type == "artifact"
        and resource.status not in {None, "clean"}
        and action in {"read", "download"}
    ):
        if _could_read(principal, resource):
            return _deny(409, "artifact_not_clean")
        return _deny(404, "not_found")
    if principal.kind == "agent" and action == "execute_tool":
        return (
            _ok() if _agent_tool_allowed(principal, resource) else _deny(403, "permission_denied")
        )
    if principal.workspace_role == "guest" and action in {
        "create",
        "run",
        "execute_tool",
        "update",
        "delete",
    }:
        return _deny(403, "permission_denied")
    if (
        principal.kind == "pat"
        and "chat.read" in principal.scopes
        and action not in {"read", "list"}
    ):
        return _deny(403, "permission_denied")
    if principal.kind == "mcp_client" and action == "execute_tool":
        if "tools.invoke" in principal.scopes:
            return _ok()
        return _deny(403, "permission_denied")
    if resource.type in {"audit_log", "budget"}:
        if principal.workspace_role in {"owner", "admin"} and action in {
            "read",
            "list",
            "update",
            "create",
        }:
            if resource.type == "budget" or action in {"read", "list"}:
                return _ok()
            if principal.workspace_role == "owner" or action != "delete":
                return _ok()
        if principal.workspace_id != resource.workspace_id:
            return _deny(404, "not_found")
        return _deny(403, "permission_denied")
    if resource.private and principal.user_id != resource.owner_user_id:
        if principal.workspace_id != resource.workspace_id:
            return _deny(404, "not_found")
        return _deny(403, "permission_denied")
    if principal.kind == "share_link":
        if not resource.link_visible:
            return _deny(404, "not_found")
        if action in {"read", "list"}:
            return _ok()
        if action == "update" and principal.share_role == "commenter" and resource.type == "chat":
            return _deny(403, "permission_denied")
        return _deny(403, "permission_denied")
    rank = max(
        _role_rank(_workspace_ceiling(principal, resource)),
        _role_rank(resource.grant_role if principal.user_id else None),
    )
    if (
        principal.user_id
        and resource.owner_user_id == principal.user_id
        and principal.workspace_role in {"owner", "admin", "member", "guest"}
    ):
        rank = max(rank, _RANK["owner"])
    if action in {"read", "list"}:
        return _ok() if rank >= _RANK["viewer"] else _missing(principal, resource)
    if action == "create":
        if (
            principal.workspace_role in {"owner", "admin", "member"}
            and principal.workspace_id == resource.workspace_id
        ):
            return _ok()
        return _missing(principal, resource)
    if action in {"update", "share", "run", "execute_tool", "decide_approval"}:
        if rank >= _RANK["editor"] or (
            action == "decide_approval" and principal.workspace_role in {"owner", "admin", "member"}
        ):
            return _ok()
        return _missing(principal, resource)
    if action == "delete":
        if rank >= _RANK["owner"]:
            return _ok()
        return _missing(principal, resource)
    return _missing(principal, resource)


def _agent_tool_allowed(principal: Principal, resource: ResourceView) -> bool:
    if principal.workspace_role not in {"owner", "admin", "member"}:
        return False
    key = resource.tool_key or ""
    return key in principal.tool_allowlist


def _could_read(principal: Principal, resource: ResourceView) -> bool:
    probe = ResourceView(
        type=resource.type,
        id=resource.id,
        workspace_id=resource.workspace_id,
        owner_user_id=resource.owner_user_id,
        archived=False,
        grant_role=resource.grant_role,
        link_visible=resource.link_visible,
        status="clean",
        private=resource.private,
    )
    return decide(principal, "read", probe).allowed


def _missing(principal: Principal, resource: ResourceView) -> Decision:
    if principal.workspace_id is None or resource.workspace_id is None:
        return _deny(404, "not_found")
    if principal.workspace_id != resource.workspace_id:
        return _deny(404, "not_found")
    if principal.workspace_role is None:
        return _deny(404, "not_found")
    return _deny(403, "permission_denied")
