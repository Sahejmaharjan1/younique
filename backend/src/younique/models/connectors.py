from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    LargeBinary,
    Text,
    Uuid,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from younique.models.base import AuditColumns, Base, SoftDelete, UUIDPrimaryKey


class Connection(UUIDPrimaryKey, AuditColumns, SoftDelete, Base):
    __tablename__ = "connections"
    __table_args__ = (
        CheckConstraint(
            "status IN ('pending','active','needs_reauth','revoked','error')",
            name="status",
        ),
        CheckConstraint("health IN ('healthy','degraded','failing','unknown')", name="health"),
        {"schema": "app"},
    )
    workspace_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("app.workspaces.id"), nullable=False
    )
    connector_key: Mapped[str] = mapped_column(Text, nullable=False)
    owner_user_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("app.users.id"), nullable=False)
    external_account_id: Mapped[str | None] = mapped_column(Text, nullable=True)
    external_account_label: Mapped[str | None] = mapped_column(Text, nullable=True)
    granted_scopes: Mapped[list[str]] = mapped_column(
        JSONB, nullable=False, server_default=text("'[]'::jsonb")
    )
    enabled_bundles: Mapped[list[str]] = mapped_column(
        JSONB, nullable=False, server_default=text("'[]'::jsonb")
    )
    status: Mapped[str] = mapped_column(Text, nullable=False, server_default="pending")
    health: Mapped[str] = mapped_column(Text, nullable=False, server_default="unknown")
    last_checked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    uses_byo_oauth_client: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="false")
    config: Mapped[dict[str, object]] = mapped_column(
        JSONB, nullable=False, server_default=text("'{}'::jsonb")
    )


class ConnectionGrant(UUIDPrimaryKey, Base):
    __tablename__ = "connection_grants"
    __table_args__ = ({"schema": "app"},)
    workspace_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("app.workspaces.id"), nullable=False
    )
    connection_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("app.connections.id", ondelete="CASCADE"), nullable=False
    )
    resource_kind: Mapped[str] = mapped_column(Text, nullable=False)
    resource_ref: Mapped[str] = mapped_column(Text, nullable=False)
    allowed_actions: Mapped[list[str]] = mapped_column(JSONB, nullable=False)


class ConnectionSecret(UUIDPrimaryKey, Base):
    __tablename__ = "connection_secrets"
    __table_args__ = (
        Index("uq_connection_secret", "connection_id", unique=True),
        {"schema": "app"},
    )
    workspace_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("app.workspaces.id"), nullable=False
    )
    connection_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("app.connections.id", ondelete="CASCADE"), nullable=False
    )
    encryption_key_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("app.encryption_keys.id"), nullable=False
    )
    access_token_ct: Mapped[bytes | None] = mapped_column(LargeBinary, nullable=True)
    refresh_token_ct: Mapped[bytes | None] = mapped_column(LargeBinary, nullable=True)
    secret_ct: Mapped[bytes | None] = mapped_column(LargeBinary, nullable=True)
    access_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    key_version: Mapped[int] = mapped_column(Integer, nullable=False, server_default="1")


class OAuthState(UUIDPrimaryKey, Base):
    __tablename__ = "oauth_states"
    __table_args__ = ({"schema": "app"},)
    workspace_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("app.workspaces.id"), nullable=False
    )
    user_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("app.users.id"), nullable=False)
    connector_key: Mapped[str] = mapped_column(Text, nullable=False)
    state_hash: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    pkce_verifier_ct: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    encryption_key_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("app.encryption_keys.id"), nullable=False
    )
    key_version: Mapped[int] = mapped_column(Integer, nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class OAuthClient(UUIDPrimaryKey, AuditColumns, Base):
    __tablename__ = "oauth_clients"
    __table_args__ = (
        Index("uq_oauth_client_ws", "workspace_id", "connector_key", unique=True),
        {"schema": "app"},
    )
    workspace_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("app.workspaces.id"), nullable=False
    )
    connector_key: Mapped[str] = mapped_column(Text, nullable=False)
    client_id: Mapped[str] = mapped_column(Text, nullable=False)
    client_secret_ct: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    encryption_key_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("app.encryption_keys.id"), nullable=False
    )
    key_version: Mapped[int] = mapped_column(Integer, nullable=False)


class WebhookNonce(UUIDPrimaryKey, Base):
    __tablename__ = "webhook_nonces"
    __table_args__ = (
        Index("uq_webhook_nonce", "connection_id", "nonce", unique=True),
        {"schema": "app"},
    )
    workspace_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("app.workspaces.id"), nullable=False
    )
    connection_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("app.connections.id", ondelete="CASCADE"), nullable=False
    )
    nonce: Mapped[str] = mapped_column(Text, nullable=False)
    seen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class ResourceGrant(UUIDPrimaryKey, Base):
    __tablename__ = "resource_grants"
    __table_args__ = (
        CheckConstraint(
            "resource_type IN ('chat','artifact','agent','pipeline','memory_set')",
            name="resource_type",
        ),
        CheckConstraint("subject_type IN ('user','email','workspace','link')", name="subject_type"),
        CheckConstraint("role IN ('owner','editor','commenter','viewer')", name="role"),
        Index(
            "ix_grants_subject",
            "subject_user_id",
            "resource_type",
            "resource_id",
            postgresql_where=text("revoked_at IS NULL"),
        ),
        Index(
            "ix_grants_resource",
            "resource_type",
            "resource_id",
            postgresql_where=text("revoked_at IS NULL"),
        ),
        {"schema": "app"},
    )
    workspace_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("app.workspaces.id"), nullable=False
    )
    resource_type: Mapped[str] = mapped_column(Text, nullable=False)
    resource_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False)
    subject_type: Mapped[str] = mapped_column(Text, nullable=False)
    subject_user_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("app.users.id"), nullable=True
    )
    subject_email: Mapped[str | None] = mapped_column(Text, nullable=True)
    share_link_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True)
    role: Mapped[str] = mapped_column(Text, nullable=False)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class ShareLink(UUIDPrimaryKey, Base):
    __tablename__ = "share_links"
    __table_args__ = (
        CheckConstraint("role IN ('viewer','commenter')", name="role"),
        {"schema": "app"},
    )
    workspace_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("app.workspaces.id"), nullable=False
    )
    resource_type: Mapped[str] = mapped_column(Text, nullable=False)
    resource_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False)
    token_hash: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    role: Mapped[str] = mapped_column(Text, nullable=False, server_default="viewer")
    password_hash: Mapped[str | None] = mapped_column(Text, nullable=True)
    include_reasoning: Mapped[bool] = mapped_column(nullable=False, server_default="false")
    include_cost: Mapped[bool] = mapped_column(nullable=False, server_default="false")
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    view_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    last_viewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_by: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("app.users.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
