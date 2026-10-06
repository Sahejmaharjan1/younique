from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Text,
    Uuid,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import INET, JSONB
from sqlalchemy.orm import Mapped, mapped_column

from younique.models.base import AuditColumns, Base, SoftDelete, UUIDPrimaryKey


class User(UUIDPrimaryKey, AuditColumns, SoftDelete, Base):
    __tablename__ = "users"
    __table_args__ = ({"schema": "app"},)
    primary_email: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    display_name: Mapped[str] = mapped_column(Text, nullable=False)
    timezone: Mapped[str] = mapped_column(Text, nullable=False, server_default="UTC")
    default_workspace_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid,
        ForeignKey("app.workspaces.id", use_alter=True, name="fk_users_default_workspace"),
        nullable=True,
    )
    preferences: Mapped[dict[str, object]] = mapped_column(
        JSONB, nullable=False, server_default=text("'{}'::jsonb")
    )


class Identity(UUIDPrimaryKey, Base):
    __tablename__ = "identities"
    __table_args__ = (
        CheckConstraint("provider IN ('google','github','password')", name="provider"),
        {"schema": "app"},
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("app.users.id", ondelete="CASCADE"), nullable=False
    )
    provider: Mapped[str] = mapped_column(Text, nullable=False)
    firebase_uid: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    provider_subject: Mapped[str] = mapped_column(Text, nullable=False)
    is_primary: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="false")
    email: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class Device(UUIDPrimaryKey, Base):
    __tablename__ = "devices"
    __table_args__ = ({"schema": "app"},)
    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("app.users.id", ondelete="CASCADE"), nullable=False
    )
    fingerprint_hash: Mapped[str] = mapped_column(Text, nullable=False)
    user_agent: Mapped[str] = mapped_column(Text, nullable=False, server_default="")
    last_ip: Mapped[str | None] = mapped_column(INET, nullable=True)
    last_seen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class Session(UUIDPrimaryKey, Base):
    __tablename__ = "sessions"
    __table_args__ = (
        Index("uq_sessions_token", "token_hash", unique=True),
        Index("ix_sessions_user_active", "user_id", postgresql_where=text("revoked_at IS NULL")),
        Index("ix_sessions_group", "session_group_id"),
        {"schema": "app"},
    )
    user_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("app.users.id"), nullable=False)
    device_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("app.devices.id"), nullable=False)
    token_hash: Mapped[str] = mapped_column(Text, nullable=False)
    session_group_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False)
    active_workspace_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("app.workspaces.id"), nullable=True
    )
    csrf_hash: Mapped[str] = mapped_column(Text, nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    absolute_expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    revoked_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    reauthed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_seen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class Workspace(UUIDPrimaryKey, AuditColumns, SoftDelete, Base):
    __tablename__ = "workspaces"
    __table_args__ = (
        CheckConstraint("plan IN ('free','pro')", name="plan"),
        {"schema": "app"},
    )
    slug: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    plan: Mapped[str] = mapped_column(Text, nullable=False, server_default="free")
    settings: Mapped[dict[str, object]] = mapped_column(
        JSONB, nullable=False, server_default=text("'{}'::jsonb")
    )


class WorkspaceMember(UUIDPrimaryKey, AuditColumns, SoftDelete, Base):
    __tablename__ = "workspace_members"
    __table_args__ = (
        CheckConstraint("role IN ('owner','admin','member','guest')", name="role"),
        Index(
            "uq_member_ws_user",
            "workspace_id",
            "user_id",
            unique=True,
            postgresql_where=text("archived_at IS NULL"),
        ),
        {"schema": "app"},
    )
    workspace_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("app.workspaces.id"), nullable=False
    )
    user_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("app.users.id"), nullable=False)
    role: Mapped[str] = mapped_column(Text, nullable=False)


class Invitation(UUIDPrimaryKey, Base):
    __tablename__ = "invitations"
    __table_args__ = (
        CheckConstraint("role IN ('admin','member','guest')", name="role"),
        {"schema": "app"},
    )
    workspace_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("app.workspaces.id"), nullable=False
    )
    email: Mapped[str] = mapped_column(Text, nullable=False)
    role: Mapped[str] = mapped_column(Text, nullable=False)
    token_hash: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    accepted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class ConsentDocument(UUIDPrimaryKey, Base):
    __tablename__ = "consent_documents"
    __table_args__ = (
        CheckConstraint("kind IN ('terms','privacy','dpa','ai_data_use')", name="kind"),
        Index("uq_consent_kind_version", "kind", "version", unique=True),
        {"schema": "app"},
    )
    kind: Mapped[str] = mapped_column(Text, nullable=False)
    version: Mapped[int] = mapped_column(nullable=False)
    content_sha256: Mapped[str] = mapped_column(Text, nullable=False)
    summary_of_changes: Mapped[str] = mapped_column(Text, nullable=False, server_default="")
    url: Mapped[str] = mapped_column(Text, nullable=False)
    is_required: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="true")
    effective_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class ConsentAcceptance(UUIDPrimaryKey, Base):
    __tablename__ = "consent_acceptances"
    __table_args__ = ({"schema": "app"},)
    user_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("app.users.id"), nullable=False)
    consent_document_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("app.consent_documents.id"), nullable=False
    )
    accepted_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    ip: Mapped[str | None] = mapped_column(INET, nullable=True)
    user_agent: Mapped[str] = mapped_column(Text, nullable=False, server_default="")
    content_sha256: Mapped[str] = mapped_column(Text, nullable=False)
