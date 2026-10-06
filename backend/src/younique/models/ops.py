from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    LargeBinary,
    PrimaryKeyConstraint,
    Text,
    Uuid,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column
from uuid6 import uuid7

from younique.models.base import AuditColumns, Base, SoftDelete, UUIDPrimaryKey


class EncryptionKey(UUIDPrimaryKey, Base):
    __tablename__ = "encryption_keys"
    __table_args__ = (
        Index("uq_encryption_keys_ws_version", "workspace_id", "version", unique=True),
        {"schema": "app"},
    )
    workspace_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("app.workspaces.id"), nullable=False
    )
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    dek_wrapped: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    kms_key_name: Mapped[str] = mapped_column(Text, nullable=False)
    rotated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class IdempotencyKey(UUIDPrimaryKey, Base):
    __tablename__ = "idempotency_keys"
    __table_args__ = (
        CheckConstraint("state IN ('in_flight','completed')", name="state"),
        Index(
            "uq_idem",
            "workspace_id",
            "user_id",
            "endpoint",
            "key",
            unique=True,
        ),
        {"schema": "app"},
    )
    workspace_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("app.workspaces.id"), nullable=False
    )
    user_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("app.users.id"), nullable=False)
    key: Mapped[str] = mapped_column(Text, nullable=False)
    endpoint: Mapped[str] = mapped_column(Text, nullable=False)
    request_sha256: Mapped[str] = mapped_column(Text, nullable=False)
    response_status: Mapped[int | None] = mapped_column(Integer, nullable=True)
    response_body: Mapped[dict[str, object] | None] = mapped_column(JSONB, nullable=True)
    state: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class Outbox(UUIDPrimaryKey, Base):
    __tablename__ = "outbox"
    __table_args__ = (
        Index("ix_outbox_unpublished", "created_at", postgresql_where=text("published_at IS NULL")),
        {"schema": "app"},
    )
    workspace_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("app.workspaces.id"), nullable=True
    )
    topic: Mapped[str] = mapped_column(Text, nullable=False)
    payload: Mapped[dict[str, object]] = mapped_column(JSONB, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)


class MemorySet(UUIDPrimaryKey, AuditColumns, SoftDelete, Base):
    __tablename__ = "memory_sets"
    __table_args__ = (
        CheckConstraint("scope IN ('personal','workspace','project','chat')", name="scope"),
        CheckConstraint("write_mode IN ('off','append','overwrite')", name="write_mode"),
        {"schema": "app"},
    )
    workspace_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("app.workspaces.id"), nullable=False
    )
    scope: Mapped[str] = mapped_column(Text, nullable=False)
    owner_user_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("app.users.id"), nullable=True
    )
    name: Mapped[str] = mapped_column(Text, nullable=False)
    write_mode: Mapped[str] = mapped_column(Text, nullable=False, server_default="append")


class ModelProvider(UUIDPrimaryKey, Base):
    __tablename__ = "model_providers"
    __table_args__ = ({"schema": "app"},)
    key: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    display_name: Mapped[str] = mapped_column(Text, nullable=False)
    auth_kind: Mapped[str] = mapped_column(Text, nullable=False)


class Model(UUIDPrimaryKey, Base):
    __tablename__ = "models"
    __table_args__ = (
        CheckConstraint(
            "reasoning_control IN ('none','boolean','effort','budget_tokens')",
            name="reasoning_control",
        ),
        CheckConstraint("status IN ('active','preview','deprecated','retired')", name="status"),
        Index("uq_models_ref", "provider_id", "model_ref", "workspace_id", unique=True),
        {"schema": "app"},
    )
    provider_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("app.model_providers.id"), nullable=False
    )
    workspace_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("app.workspaces.id"), nullable=True
    )
    model_ref: Mapped[str] = mapped_column(Text, nullable=False)
    display_name: Mapped[str] = mapped_column(Text, nullable=False)
    context_window: Mapped[int] = mapped_column(Integer, nullable=False)
    max_output_tokens: Mapped[int] = mapped_column(Integer, nullable=False)
    supports_tools: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="false")
    supports_reasoning: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default="false"
    )
    supports_vision: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="false")
    reasoning_control: Mapped[str] = mapped_column(Text, nullable=False, server_default="none")
    status: Mapped[str] = mapped_column(Text, nullable=False, server_default="active")
    capabilities: Mapped[dict[str, object]] = mapped_column(
        JSONB, nullable=False, server_default=text("'{}'::jsonb")
    )


class ModelPrice(UUIDPrimaryKey, Base):
    __tablename__ = "model_prices"
    __table_args__ = ({"schema": "app"},)
    model_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("app.models.id"), nullable=False)
    input_micro_usd_per_mtok: Mapped[int] = mapped_column(BigInteger, nullable=False)
    output_micro_usd_per_mtok: Mapped[int] = mapped_column(BigInteger, nullable=False)
    cached_input_micro_usd_per_mtok: Mapped[int] = mapped_column(BigInteger, nullable=False)
    reasoning_micro_usd_per_mtok: Mapped[int] = mapped_column(BigInteger, nullable=False)
    effective_from: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class ProviderKey(UUIDPrimaryKey, AuditColumns, Base):
    __tablename__ = "provider_keys"
    __table_args__ = (
        CheckConstraint("status IN ('active','invalid','revoked')", name="status"),
        {"schema": "app"},
    )
    workspace_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("app.workspaces.id"), nullable=False
    )
    provider_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("app.model_providers.id"), nullable=False
    )
    owner_user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("app.users.id"), nullable=False
    )
    label: Mapped[str] = mapped_column(Text, nullable=False)
    last4: Mapped[str] = mapped_column(Text, nullable=False)
    key_ct: Mapped[bytes | None] = mapped_column(LargeBinary, nullable=True)
    encryption_key_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("app.encryption_keys.id"), nullable=True
    )
    key_version: Mapped[int] = mapped_column(Integer, nullable=False, server_default="1")
    base_url_override: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(Text, nullable=False, server_default="active")
    last_validated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class Pat(UUIDPrimaryKey, Base):
    __tablename__ = "pats"
    __table_args__ = ({"schema": "app"},)
    workspace_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("app.workspaces.id"), nullable=True
    )
    user_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("app.users.id"), nullable=False)
    token_hash: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    label: Mapped[str] = mapped_column(Text, nullable=False)
    scopes: Mapped[list[str]] = mapped_column(JSONB, nullable=False)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class UsageEvent(Base):
    __tablename__ = "usage_events"
    __table_args__ = (
        PrimaryKeyConstraint("id", "occurred_at", name="pk_usage_events"),
        Index("ix_usage_ws_time", "workspace_id", "occurred_at"),
        Index("ix_usage_run", "run_id"),
        {"schema": "app", "postgresql_partition_by": "RANGE (occurred_at)"},
    )
    id: Mapped[uuid.UUID] = mapped_column(Uuid, default=uuid7)
    workspace_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("app.workspaces.id"), nullable=False
    )
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    run_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True)
    run_step_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True)
    chat_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True)
    model_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("app.models.id"), nullable=True
    )
    provider_key_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True)
    input_tokens: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    cached_input_tokens: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    output_tokens: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    reasoning_tokens: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    cost_micro_usd: Mapped[int] = mapped_column(BigInteger, nullable=False)
    price_snapshot: Mapped[dict[str, object]] = mapped_column(JSONB, nullable=False)
    request_id: Mapped[str] = mapped_column(Text, nullable=False)


class UsageRequestDedupe(Base):
    __tablename__ = "usage_request_dedupe"
    __table_args__ = ({"schema": "app"},)
    request_id: Mapped[str] = mapped_column(Text, primary_key=True)
    workspace_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("app.workspaces.id"), nullable=False
    )
    usage_event_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False)


class AuditLog(Base):
    __tablename__ = "audit_logs"
    __table_args__ = (
        PrimaryKeyConstraint("id", "occurred_at", name="pk_audit_logs"),
        CheckConstraint("outcome IN ('allowed','denied','error')", name="outcome"),
        Index("ix_audit_ws_time", "workspace_id", "occurred_at"),
        {"schema": "audit", "postgresql_partition_by": "RANGE (occurred_at)"},
    )
    id: Mapped[uuid.UUID] = mapped_column(Uuid, default=uuid7)
    workspace_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    actor_user_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True)
    actor_kind: Mapped[str] = mapped_column(Text, nullable=False)
    action: Mapped[str] = mapped_column(Text, nullable=False)
    resource_type: Mapped[str] = mapped_column(Text, nullable=False)
    resource_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True)
    outcome: Mapped[str] = mapped_column(Text, nullable=False)
    ip: Mapped[str | None] = mapped_column(Text, nullable=True)
    user_agent: Mapped[str | None] = mapped_column(Text, nullable=True)
    detail_redacted: Mapped[dict[str, object]] = mapped_column(
        JSONB, nullable=False, server_default=text("'{}'::jsonb")
    )
    request_id: Mapped[str | None] = mapped_column(Text, nullable=True)
