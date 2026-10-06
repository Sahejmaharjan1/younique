from __future__ import annotations

import base64
import hashlib
import hmac
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from younique.artifacts.pipeline import (
    Placement,
    content_disposition,
    place_upload,
    resumable_upload_url,
)
from younique.artifacts.scan import ScanResult
from younique.artifacts.store import get_store
from younique.authz.principal import Principal
from younique.core.config import Settings
from younique.core.errors import artifact_not_clean, not_found, problem
from younique.events.outbox import append_outbox
from younique.models import Artifact, ArtifactScan, ArtifactVersion, ChatArtifact


def upload_token(version_id: UUID, byte_size: int, settings: Settings) -> str:
    secret = (settings.upload_token_secret or settings.dev_internal_token).encode()
    message = f"{version_id}:{byte_size}".encode()
    return hmac.new(secret, message, hashlib.sha256).hexdigest()


def token_matches(token: str, version_id: UUID, byte_size: int, settings: Settings) -> bool:
    expected = upload_token(version_id, byte_size, settings)
    return hmac.compare_digest(token, expected)


async def reserve_upload(
    db: AsyncSession,
    principal: Principal,
    *,
    name: str,
    declared_mime: str,
    byte_size: int,
    settings: Settings,
    chat_id: UUID | None = None,
) -> dict[str, object]:
    if principal.workspace_id is None:
        raise not_found()
    if byte_size < 1 or byte_size > settings.max_upload_bytes:
        raise problem(
            413,
            "file_too_large",
            "File too large",
            "Uploads must be between 1 byte and 100 MB.",
            remediation={
                "message": "Choose a smaller file.",
                "action": "retry",
                "href": "/artifacts",
            },
        )
    artifact = Artifact(
        workspace_id=principal.workspace_id,
        name=name,
        origin="uploaded",
        total_bytes=byte_size,
        created_by=principal.user_id,
    )
    db.add(artifact)
    await db.flush()
    object_name = f"staging/{principal.workspace_id}/{artifact.id}"
    version = ArtifactVersion(
        workspace_id=principal.workspace_id,
        artifact_id=artifact.id,
        version=1,
        gcs_bucket=settings.gcs_uploads_bucket,
        gcs_object=object_name,
        declared_mime=declared_mime,
        byte_size=byte_size,
        sha256=f"pending-{artifact.id}",
        status="pending",
    )
    db.add(version)
    await db.flush()
    artifact.current_version_id = version.id
    if chat_id is not None:
        await _link_chat(db, principal.workspace_id, chat_id, artifact.id)
    gcs_url = resumable_upload_url(settings, settings.gcs_uploads_bucket, object_name, byte_size)
    api_path = f"/v1/artifacts/{artifact.id}/content"
    upload_url = gcs_url if settings.gcs_mode == "http" else api_path
    return {
        "artifact_id": str(artifact.id),
        "version_id": str(version.id),
        "version": version.version,
        "status": version.status,
        "upload_url": upload_url,
        "gcs_upload_url": gcs_url,
        "upload_token": upload_token(version.id, byte_size, settings),
        "byte_size": byte_size,
    }


async def accept_upload(
    db: AsyncSession,
    principal: Principal,
    artifact_id: UUID,
    data: bytes,
    *,
    token: str,
    settings: Settings,
    timeout_s: float = 30,
) -> ArtifactVersion:
    version = await _latest(db, artifact_id)
    if version is None or principal.workspace_id is None:
        raise not_found()
    if not token_matches(token, version.id, version.byte_size, settings):
        raise problem(
            403,
            "permission_denied",
            "Permission denied",
            "The upload token does not match this artifact.",
        )
    if len(data) > version.byte_size or len(data) > settings.max_upload_bytes:
        raise problem(
            413, "file_too_large", "File too large", "The upload exceeded the reserved size."
        )
    if len(data) != version.byte_size:
        raise problem(
            422,
            "validation_failed",
            "Validation failed",
            "The upload length does not match the reservation.",
        )
    artifact = (
        await db.execute(select(Artifact).where(Artifact.id == artifact_id))
    ).scalar_one_or_none()
    if artifact is None:
        raise not_found()
    return await apply_bytes(
        db, principal, artifact, version, data, settings=settings, timeout_s=timeout_s
    )


async def ingest_inline(
    db: AsyncSession,
    principal: Principal,
    *,
    name: str,
    declared_mime: str,
    data: bytes,
    settings: Settings,
    timeout_s: float = 30,
    chat_id: UUID | None = None,
) -> ArtifactVersion:
    if principal.workspace_id is None:
        raise not_found()
    if len(data) > settings.max_upload_bytes:
        raise problem(413, "file_too_large", "File too large", "Uploads must be 100 MB or smaller.")
    digest = hashlib.sha256(data).hexdigest()
    existing = (
        await db.execute(
            select(ArtifactVersion).where(
                ArtifactVersion.workspace_id == principal.workspace_id,
                ArtifactVersion.sha256 == digest,
            )
        )
    ).scalar_one_or_none()
    if existing is not None:
        return existing
    artifact = Artifact(
        workspace_id=principal.workspace_id,
        name=name,
        origin="uploaded",
        total_bytes=len(data),
        created_by=principal.user_id,
    )
    db.add(artifact)
    await db.flush()
    version = ArtifactVersion(
        workspace_id=principal.workspace_id,
        artifact_id=artifact.id,
        version=1,
        gcs_bucket=settings.gcs_uploads_bucket,
        gcs_object=f"staging/{principal.workspace_id}/{artifact.id}",
        declared_mime=declared_mime,
        byte_size=len(data),
        sha256=f"pending-{artifact.id}",
        status="pending",
    )
    db.add(version)
    await db.flush()
    artifact.current_version_id = version.id
    if chat_id is not None:
        await _link_chat(db, principal.workspace_id, chat_id, artifact.id)
    return await apply_bytes(
        db, principal, artifact, version, data, settings=settings, timeout_s=timeout_s
    )


async def apply_bytes(
    db: AsyncSession,
    principal: Principal,
    artifact: Artifact,
    version: ArtifactVersion,
    data: bytes,
    *,
    settings: Settings,
    timeout_s: float = 30,
    scanned: ScanResult | None = None,
) -> ArtifactVersion:
    if principal.workspace_id is None:
        raise not_found()
    from younique.scanner.app import inspect_upload

    digest = hashlib.sha256(data).hexdigest()
    if scanned is None:
        scanned = await inspect_upload(
            data,
            name=artifact.name,
            declared_mime=version.declared_mime,
            timeout_s=timeout_s,
        )
    duplicate = (
        await db.execute(
            select(ArtifactVersion).where(
                ArtifactVersion.workspace_id == principal.workspace_id,
                ArtifactVersion.sha256 == digest,
                ArtifactVersion.id != version.id,
            )
        )
    ).scalar_one_or_none()
    if duplicate is not None:
        version.status = "failed"
        version.detected_mime = duplicate.detected_mime
        version.preview_meta = {"duplicate_of": str(duplicate.artifact_id)}
        artifact.current_version_id = version.id
        return duplicate
    placement = place_upload(
        get_store(),
        data=data,
        name=artifact.name,
        declared_mime=version.declared_mime,
        workspace_id=str(principal.workspace_id),
        artifact_id=str(artifact.id),
        uploads_bucket=settings.gcs_uploads_bucket,
        artifacts_bucket=settings.gcs_artifacts_bucket,
        timeout_s=timeout_s,
        scanned=scanned,
    )
    _write_placement(artifact, version, placement)
    db.add(
        ArtifactScan(
            workspace_id=principal.workspace_id,
            artifact_version_id=version.id,
            engine="clamav" if settings.scanner_mode == "clamav" else "builtin",
            engine_version="1",
            result="error" if placement.status == "failed" else placement.status,
            signature=placement.signature,
        )
    )
    topic = "artifact.ready" if placement.status == "clean" else f"artifact.{placement.status}"
    await append_outbox(
        db,
        workspace_id=principal.workspace_id,
        topic="events",
        payload={"type": topic, "artifact_id": str(artifact.id), "status": placement.status},
    )
    await db.flush()
    return version


def _write_placement(artifact: Artifact, version: ArtifactVersion, placement: Placement) -> None:
    version.status = placement.status
    version.gcs_bucket = placement.bucket
    version.gcs_object = placement.object_key
    version.detected_mime = placement.detected_mime
    version.sha256 = placement.sha256
    version.byte_size = version.byte_size or 0
    version.preview_meta = placement.preview
    artifact.current_version_id = version.id
    artifact.total_bytes = version.byte_size


def download_payload(version: ArtifactVersion, *, name: str) -> dict[str, object]:
    if version.status != "clean":
        raise artifact_not_clean(version.status)
    return {
        "url": f"https://downloads.younique.local/{version.gcs_object}",
        "expires_in": 300,
        "content_disposition": content_disposition(name, version.detected_mime),
    }


async def list_artifacts(
    db: AsyncSession,
    principal: Principal,
    *,
    chat_id: UUID | None = None,
    status: str | None = None,
    origin: str | None = None,
) -> list[dict[str, object]]:
    if principal.workspace_id is None:
        return []
    stmt = select(Artifact).where(
        Artifact.workspace_id == principal.workspace_id, Artifact.archived_at.is_(None)
    )
    if origin:
        stmt = stmt.where(Artifact.origin == origin)
    if chat_id is not None:
        linked = select(ChatArtifact.artifact_id).where(ChatArtifact.chat_id == chat_id)
        stmt = stmt.where(Artifact.id.in_(linked))
    rows = (await db.execute(stmt.order_by(Artifact.created_at.desc()))).scalars().all()
    found: list[dict[str, object]] = []
    for artifact in rows:
        version = await _latest(db, artifact.id)
        if version is None:
            continue
        if status and version.status != status:
            continue
        found.append(_view(artifact, version))
    return found


async def artifact_detail(db: AsyncSession, artifact_id: UUID) -> dict[str, object]:
    artifact = (
        await db.execute(select(Artifact).where(Artifact.id == artifact_id))
    ).scalar_one_or_none()
    version = await _latest(db, artifact_id)
    if artifact is None or version is None:
        raise not_found()
    return _view(artifact, version)


async def preview_payload(db: AsyncSession, artifact_id: UUID) -> dict[str, object]:
    version = await _latest(db, artifact_id)
    if version is None:
        raise not_found()
    if version.status != "clean":
        return {"status": version.status, "preview": None}
    return {
        "status": "clean",
        "preview": version.preview_meta,
        "detected_mime": version.detected_mime,
    }


def decode_body(raw: str | None) -> bytes:
    if not raw:
        return b""
    return base64.b64decode(raw)


async def _latest(db: AsyncSession, artifact_id: UUID) -> ArtifactVersion | None:
    return (
        (
            await db.execute(
                select(ArtifactVersion)
                .where(ArtifactVersion.artifact_id == artifact_id)
                .order_by(ArtifactVersion.version.desc())
            )
        )
        .scalars()
        .first()
    )


async def _link_chat(
    db: AsyncSession, workspace_id: UUID, chat_id: UUID, artifact_id: UUID
) -> None:
    existing = (
        await db.execute(
            select(ChatArtifact).where(
                ChatArtifact.chat_id == chat_id, ChatArtifact.artifact_id == artifact_id
            )
        )
    ).scalar_one_or_none()
    if existing is None:
        db.add(ChatArtifact(workspace_id=workspace_id, chat_id=chat_id, artifact_id=artifact_id))


def _view(artifact: Artifact, version: ArtifactVersion) -> dict[str, object]:
    return {
        "id": str(artifact.id),
        "name": artifact.name,
        "origin": artifact.origin,
        "status": version.status,
        "detected_mime": version.detected_mime,
        "declared_mime": version.declared_mime,
        "byte_size": version.byte_size,
        "sha256": version.sha256,
        "version_id": str(version.id),
        "preview": version.preview_meta if version.status == "clean" else None,
        "created_at": artifact.created_at.isoformat()
        if artifact.created_at
        else datetime.now(UTC).isoformat(),
    }


def gcs_push_body(body: dict[str, Any]) -> dict[str, Any]:
    message = body.get("message")
    if isinstance(message, dict) and isinstance(message.get("data"), str):
        import json

        decoded = base64.b64decode(message["data"])
        parsed = json.loads(decoded)
        if isinstance(parsed, dict):
            return parsed
    return body
