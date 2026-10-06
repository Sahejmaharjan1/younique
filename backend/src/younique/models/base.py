from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, MetaData, Uuid, func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from uuid6 import uuid7

NAMING = {
    "ix": "ix_%(table_name)s_%(column_0_name)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


class Base(DeclarativeBase):
    metadata = MetaData(naming_convention=NAMING)


class UUIDPrimaryKey:
    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid7)


class AuditColumns:
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    created_by: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True)
    updated_by: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True)


class SoftDelete:
    archived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    archived_by: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True)


TENANT_TABLES: tuple[str, ...] = (
    "workspaces",
    "workspace_members",
    "invitations",
    "encryption_keys",
    "idempotency_keys",
    "outbox",
    "memory_sets",
    "chats",
    "messages",
    "message_parts",
    "runs",
    "run_steps",
    "run_events",
    "approvals",
    "tool_policies",
    "artifacts",
    "artifact_versions",
    "artifact_scans",
    "chat_artifacts",
    "provider_keys",
    "connections",
    "connection_grants",
    "connection_secrets",
    "oauth_states",
    "oauth_clients",
    "resource_grants",
    "share_links",
    "usage_events",
    "usage_request_dedupe",
    "agents",
    "agent_versions",
    "pipelines",
    "pipeline_versions",
    "pats",
    "webhook_nonces",
)

USER_SCOPED_TABLES: tuple[str, ...] = (
    "users",
    "identities",
    "devices",
    "sessions",
    "consent_acceptances",
)
