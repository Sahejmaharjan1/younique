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
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from younique.models.base import AuditColumns, Base, SoftDelete, UUIDPrimaryKey


class Artifact(UUIDPrimaryKey, AuditColumns, SoftDelete, Base):
    __tablename__ = "artifacts"
    __table_args__ = (
        CheckConstraint("origin IN ('uploaded','generated')", name="origin"),
        Index("ix_artifacts_ws_created", "workspace_id", "created_at"),
        {"schema": "app"},
    )
    workspace_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("app.workspaces.id"), nullable=False
    )
    name: Mapped[str] = mapped_column(Text, nullable=False)
    origin: Mapped[str] = mapped_column(Text, nullable=False)
    current_version_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid,
        ForeignKey("app.artifact_versions.id", use_alter=True, name="fk_artifacts_current_version"),
        nullable=True,
    )
    total_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False, server_default="0")


class ArtifactVersion(UUIDPrimaryKey, Base):
    __tablename__ = "artifact_versions"
    __table_args__ = (
        CheckConstraint(
            "status IN ('pending','scanning','clean','infected','failed')",
            name="status",
        ),
        Index("ix_artifact_versions_artifact", "artifact_id", "version"),
        Index("uq_artifact_sha", "workspace_id", "sha256", unique=True),
        {"schema": "app"},
    )
    workspace_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("app.workspaces.id"), nullable=False
    )
    artifact_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("app.artifacts.id", ondelete="CASCADE"), nullable=False
    )
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    gcs_bucket: Mapped[str] = mapped_column(Text, nullable=False)
    gcs_object: Mapped[str] = mapped_column(Text, nullable=False)
    declared_mime: Mapped[str] = mapped_column(Text, nullable=False)
    detected_mime: Mapped[str | None] = mapped_column(Text, nullable=True)
    byte_size: Mapped[int] = mapped_column(BigInteger, nullable=False)
    sha256: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(Text, nullable=False, server_default="pending")
    preview_meta: Mapped[dict[str, object] | None] = mapped_column(JSONB, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class ArtifactScan(UUIDPrimaryKey, Base):
    __tablename__ = "artifact_scans"
    __table_args__ = (
        CheckConstraint("result IN ('clean','infected','error')", name="result"),
        {"schema": "app"},
    )
    workspace_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("app.workspaces.id"), nullable=False
    )
    artifact_version_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("app.artifact_versions.id", ondelete="CASCADE"), nullable=False
    )
    engine: Mapped[str] = mapped_column(Text, nullable=False)
    engine_version: Mapped[str] = mapped_column(Text, nullable=False)
    result: Mapped[str] = mapped_column(Text, nullable=False)
    signature: Mapped[str | None] = mapped_column(Text, nullable=True)
    scanned_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class ChatArtifact(UUIDPrimaryKey, Base):
    __tablename__ = "chat_artifacts"
    __table_args__ = (
        Index("ix_chat_artifacts_artifact", "artifact_id"),
        Index("uq_chat_artifact", "chat_id", "artifact_id", unique=True),
        {"schema": "app"},
    )
    workspace_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("app.workspaces.id"), nullable=False
    )
    chat_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("app.chats.id"), nullable=False)
    artifact_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("app.artifacts.id"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
