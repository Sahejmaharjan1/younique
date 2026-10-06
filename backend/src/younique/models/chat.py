from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Text,
    Uuid,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column
from uuid6 import uuid7

from younique.models.base import AuditColumns, Base, SoftDelete, UUIDPrimaryKey


class Chat(UUIDPrimaryKey, AuditColumns, SoftDelete, Base):
    __tablename__ = "chats"
    __table_args__ = (
        CheckConstraint("reasoning_mode IN ('inherit','on','off')", name="reasoning_mode"),
        CheckConstraint(
            "memory_write_mode IN ('inherit','off','append','overwrite')",
            name="memory_write_mode",
        ),
        Index(
            "ix_chats_ws_updated",
            "workspace_id",
            text("updated_at DESC"),
            postgresql_where=text("archived_at IS NULL"),
        ),
        {"schema": "app"},
    )
    workspace_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("app.workspaces.id"), nullable=False
    )
    title: Mapped[str] = mapped_column(Text, nullable=False, server_default="New chat")
    model_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("app.models.id"), nullable=True
    )
    reasoning_mode: Mapped[str] = mapped_column(Text, nullable=False, server_default="inherit")
    memory_write_mode: Mapped[str] = mapped_column(Text, nullable=False, server_default="inherit")
    include_reasoning_on_share: Mapped[bool] = mapped_column(nullable=False, server_default="false")


class Message(UUIDPrimaryKey, AuditColumns, SoftDelete, Base):
    __tablename__ = "messages"
    __table_args__ = (
        CheckConstraint("role IN ('user','assistant','tool','system')", name="role"),
        CheckConstraint("status IN ('streaming','complete','stopped','failed')", name="status"),
        Index(
            "ix_messages_chat_seq",
            "chat_id",
            "seq",
            postgresql_where=text("archived_at IS NULL"),
        ),
        {"schema": "app"},
    )
    workspace_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("app.workspaces.id"), nullable=False
    )
    chat_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("app.chats.id", ondelete="CASCADE"), nullable=False
    )
    run_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("app.runs.id"), nullable=True)
    role: Mapped[str] = mapped_column(Text, nullable=False)
    seq: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(Text, nullable=False, server_default="complete")
    parent_message_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("app.messages.id"), nullable=True
    )
    error_code: Mapped[str | None] = mapped_column(Text, nullable=True)


class MessagePart(UUIDPrimaryKey, Base):
    __tablename__ = "message_parts"
    __table_args__ = (
        CheckConstraint(
            "kind IN ('text','reasoning','tool_call','tool_result','artifact_ref','error','citation')",
            name="kind",
        ),
        CheckConstraint("trust_level IN ('trusted','untrusted')", name="trust_level"),
        Index("ix_message_parts_message_seq", "message_id", "seq"),
        {"schema": "app"},
    )
    workspace_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("app.workspaces.id"), nullable=False
    )
    message_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("app.messages.id", ondelete="CASCADE"), nullable=False
    )
    seq: Mapped[int] = mapped_column(Integer, nullable=False)
    kind: Mapped[str] = mapped_column(Text, nullable=False)
    content: Mapped[str | None] = mapped_column(Text, nullable=True)
    data: Mapped[dict[str, object] | None] = mapped_column(JSONB, nullable=True)
    artifact_version_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True)
    trust_level: Mapped[str] = mapped_column(Text, nullable=False, server_default="trusted")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class Agent(UUIDPrimaryKey, AuditColumns, SoftDelete, Base):
    __tablename__ = "agents"
    __table_args__ = (
        CheckConstraint("kind IN ('builtin','user')", name="kind"),
        {"schema": "app"},
    )
    workspace_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("app.workspaces.id"), nullable=False
    )
    name: Mapped[str] = mapped_column(Text, nullable=False)
    kind: Mapped[str] = mapped_column(Text, nullable=False, server_default="user")
    current_version_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True)


class AgentVersion(UUIDPrimaryKey, Base):
    __tablename__ = "agent_versions"
    __table_args__ = ({"schema": "app"},)
    workspace_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("app.workspaces.id"), nullable=False
    )
    agent_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("app.agents.id"), nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    instructions: Mapped[str] = mapped_column(Text, nullable=False, server_default="")
    model_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("app.models.id"), nullable=True
    )
    tool_allowlist: Mapped[list[str]] = mapped_column(
        JSONB, nullable=False, server_default=text("'[]'::jsonb")
    )
    limits: Mapped[dict[str, object]] = mapped_column(
        JSONB, nullable=False, server_default=text("'{}'::jsonb")
    )
    reasoning_mode: Mapped[str] = mapped_column(Text, nullable=False, server_default="inherit")
    is_published: Mapped[bool] = mapped_column(nullable=False, server_default="false")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class Pipeline(UUIDPrimaryKey, AuditColumns, SoftDelete, Base):
    __tablename__ = "pipelines"
    __table_args__ = ({"schema": "app"},)
    workspace_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("app.workspaces.id"), nullable=False
    )
    name: Mapped[str] = mapped_column(Text, nullable=False)
    current_version_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True)


class PipelineVersion(UUIDPrimaryKey, Base):
    __tablename__ = "pipeline_versions"
    __table_args__ = ({"schema": "app"},)
    workspace_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("app.workspaces.id"), nullable=False
    )
    pipeline_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("app.pipelines.id"), nullable=False
    )
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    graph: Mapped[dict[str, object]] = mapped_column(
        JSONB, nullable=False, server_default=text("'{}'::jsonb")
    )
    is_published: Mapped[bool] = mapped_column(nullable=False, server_default="false")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class Run(UUIDPrimaryKey, AuditColumns, Base):
    __tablename__ = "runs"
    __table_args__ = (
        CheckConstraint(
            "kind IN ('chat','agent','pipeline')",
            name="kind",
        ),
        CheckConstraint(
            "status IN ('queued','running','awaiting_approval','paused','succeeded','failed','cancelled','expired')",
            name="status",
        ),
        CheckConstraint("trust_level IN ('trusted','untrusted')", name="trust_level"),
        CheckConstraint(
            "(kind = 'chat' AND chat_id IS NOT NULL AND agent_version_id IS NULL AND pipeline_version_id IS NULL) "
            "OR (kind = 'agent' AND agent_version_id IS NOT NULL AND pipeline_version_id IS NULL) "
            "OR (kind = 'pipeline' AND pipeline_version_id IS NOT NULL AND agent_version_id IS NULL)",
            name="kind_target",
        ),
        Index("ix_runs_ws_created", "workspace_id", "created_at"),
        Index(
            "uq_runs_idempotency",
            "idempotency_key",
            unique=True,
            postgresql_where=text("idempotency_key IS NOT NULL"),
        ),
        {"schema": "app"},
    )
    workspace_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("app.workspaces.id"), nullable=False
    )
    kind: Mapped[str] = mapped_column(Text, nullable=False)
    chat_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("app.chats.id"), nullable=True
    )
    agent_version_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("app.agent_versions.id"), nullable=True
    )
    pipeline_version_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("app.pipeline_versions.id"), nullable=True
    )
    status: Mapped[str] = mapped_column(Text, nullable=False, server_default="queued")
    trust_level: Mapped[str] = mapped_column(Text, nullable=False, server_default="trusted")
    attempt: Mapped[int] = mapped_column(Integer, nullable=False, server_default="1")
    idempotency_key: Mapped[str | None] = mapped_column(Text, nullable=True)
    error_code: Mapped[str | None] = mapped_column(Text, nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    cost_micro_usd: Mapped[int] = mapped_column(BigInteger, nullable=False, server_default="0")
    total_tokens: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class RunStep(UUIDPrimaryKey, Base):
    __tablename__ = "run_steps"
    __table_args__ = (
        CheckConstraint("kind IN ('llm','tool','transform','control','subagent')", name="kind"),
        Index("ix_run_steps_run_seq", "run_id", "seq"),
        {"schema": "app"},
    )
    workspace_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("app.workspaces.id"), nullable=False
    )
    run_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("app.runs.id", ondelete="CASCADE"), nullable=False
    )
    seq: Mapped[int] = mapped_column(Integer, nullable=False)
    node_name: Mapped[str] = mapped_column(Text, nullable=False)
    kind: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(Text, nullable=False)
    input_ref: Mapped[dict[str, object] | None] = mapped_column(JSONB, nullable=True)
    output_ref: Mapped[dict[str, object] | None] = mapped_column(JSONB, nullable=True)
    cost_micro_usd: Mapped[int] = mapped_column(BigInteger, nullable=False, server_default="0")
    duration_ms: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    error_code: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class RunEvent(Base):
    __tablename__ = "run_events"
    __table_args__ = (
        Index("ix_run_events_run_seq", "run_id", "seq", "created_at", unique=True),
        {"schema": "app", "postgresql_partition_by": "RANGE (created_at)"},
    )
    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid7)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), primary_key=True, nullable=False, server_default=func.now()
    )
    workspace_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("app.workspaces.id"), nullable=False
    )
    run_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("app.runs.id"), nullable=False)
    seq: Mapped[int] = mapped_column(Integer, nullable=False)
    event_type: Mapped[str] = mapped_column(Text, nullable=False)
    data: Mapped[dict[str, object]] = mapped_column(JSONB, nullable=False)


class Approval(UUIDPrimaryKey, AuditColumns, Base):
    __tablename__ = "approvals"
    __table_args__ = (
        CheckConstraint("risk IN ('low','medium','high')", name="risk"),
        CheckConstraint("reason IN ('policy','taint','budget')", name="reason"),
        CheckConstraint("status IN ('pending','approved','rejected','expired')", name="status"),
        Index(
            "ix_approvals_pending",
            "workspace_id",
            "created_at",
            postgresql_where=text("status = 'pending'"),
        ),
        {"schema": "app"},
    )
    workspace_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("app.workspaces.id"), nullable=False
    )
    run_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("app.runs.id"), nullable=False)
    run_step_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("app.run_steps.id"), nullable=True
    )
    tool_key: Mapped[str] = mapped_column(Text, nullable=False)
    tool_args_redacted: Mapped[dict[str, object]] = mapped_column(JSONB, nullable=False)
    summary: Mapped[dict[str, object]] = mapped_column(
        JSONB, nullable=False, server_default=text("'{}'::jsonb")
    )
    risk: Mapped[str] = mapped_column(Text, nullable=False)
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(Text, nullable=False, server_default="pending")
    decided_by: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("app.users.id"), nullable=True
    )
    decision_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class ToolPolicy(UUIDPrimaryKey, AuditColumns, Base):
    __tablename__ = "tool_policies"
    __table_args__ = (
        CheckConstraint("mode IN ('always_allow','ask_each_time','never')", name="mode"),
        Index("uq_tool_policy_scope", "workspace_id", "tool_key", "scope_agent_id", unique=True),
        {"schema": "app"},
    )
    workspace_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("app.workspaces.id"), nullable=False
    )
    scope_agent_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("app.agents.id"), nullable=True
    )
    tool_key: Mapped[str] = mapped_column(Text, nullable=False)
    mode: Mapped[str] = mapped_column(Text, nullable=False)
    allow_when_tainted: Mapped[bool] = mapped_column(nullable=False, server_default="false")
    risk: Mapped[str] = mapped_column(Text, nullable=False, server_default="high")
