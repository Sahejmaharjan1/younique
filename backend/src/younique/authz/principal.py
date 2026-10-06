from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Literal
from uuid import UUID

Role = Literal["owner", "admin", "member", "guest"]
Kind = Literal["user", "share_link", "mcp_client", "pat", "system", "agent", "anonymous"]


@dataclass(frozen=True)
class Principal:
    kind: Kind
    user_id: UUID | None = None
    workspace_id: UUID | None = None
    workspace_role: Role | None = None
    session_id: UUID | None = None
    reauthed_at: datetime | None = None
    scopes: frozenset[str] = field(default_factory=frozenset)
    share_link_id: UUID | None = None
    share_role: Literal["viewer", "commenter"] | None = None
    acting_for_run_id: UUID | None = None
    trust_level: Literal["trusted", "untrusted"] = "trusted"
    tool_allowlist: frozenset[str] = field(default_factory=frozenset)
    archived_membership: bool = False
    revoked: bool = False


@dataclass(frozen=True)
class ResourceView:
    type: str
    id: UUID | None
    workspace_id: UUID | None
    owner_user_id: UUID | None = None
    archived: bool = False
    grant_role: str | None = None
    link_visible: bool = False
    status: str | None = None
    private: bool = False
    tool_key: str | None = None


@dataclass(frozen=True)
class Decision:
    allowed: bool
    status: int
    code: str
