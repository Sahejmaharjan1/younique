from __future__ import annotations

import base64
from typing import Any
from uuid import UUID

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from younique.authz.principal import Principal
from younique.core.config import Settings
from younique.core.db import system_session
from younique.events.outbox import append_outbox, drain_outbox, get_publisher
from younique.models import Artifact, ArtifactVersion, Run
from younique.services.artifacts_flow import apply_bytes, gcs_push_body
from younique.tasks.claims import claim_run, claim_scan
from younique.tasks.outcomes import BusinessFailure, InfrastructureFailure


def _uuid(value: object, field: str) -> UUID:
    if not isinstance(value, str):
        raise BusinessFailure("validation_failed", f"{field} is required.")
    try:
        return UUID(value)
    except ValueError as exc:
        raise BusinessFailure("validation_failed", f"{field} is invalid.") from exc


def _system(workspace_id: UUID) -> Principal:
    return Principal(kind="system", workspace_id=workspace_id)


async def handle_agent_run(body: dict[str, Any], settings: Settings) -> dict[str, object]:
    return await _execute_named(body, settings, expected_kind=None)


async def handle_pipeline_run(body: dict[str, Any], settings: Settings) -> dict[str, object]:
    return await _execute_named(body, settings, expected_kind="pipeline")


async def _execute_named(
    body: dict[str, Any], settings: Settings, expected_kind: str | None
) -> dict[str, object]:
    del settings
    run_id = _uuid(body.get("run_id"), "run_id")
    workspace_id = _uuid(body.get("workspace_id"), "workspace_id")
    async with system_session(workspace_id) as session:
        run = (await session.execute(select(Run).where(Run.id == run_id))).scalar_one_or_none()
        if run is None:
            raise BusinessFailure("not_found", "Run does not exist.")
        if expected_kind is not None and run.kind != expected_kind:
            raise BusinessFailure("validation_failed", "Run kind does not match the queue.")
        if run.status != "queued":
            return {"status": "already_claimed", "run_status": run.status}
        if not await claim_run(session, run_id):
            return {"status": "already_claimed"}
        await session.refresh(run)
        await execute_run(session, run, body)
        return {"status": run.status, "code": run.error_code}
    raise InfrastructureFailure("workspace session did not open")


async def execute_run(session: AsyncSession, run: Run, body: dict[str, Any]) -> None:
    from datetime import UTC, datetime

    from younique.services.product import get_graph

    turns = body.get("turns") or [{"text": "Background run finished.", "tool_calls": []}]
    if not isinstance(turns, list):
        raise BusinessFailure("validation_failed", "turns must be a list.")
    try:
        result = await get_graph().ainvoke(
            {
                "messages": [
                    {"role": "user", "content": str(body.get("text") or ""), "trust": "trusted"}
                ],
                "run_id": str(run.id),
                "workspace_id": str(run.workspace_id),
                "trust_level": run.trust_level,
                "tool_allowlist": body.get("tool_allowlist")
                or ["smtp.send", "gmail.send_email", "gmail.get_message"],
                "policies": body.get("policies") if isinstance(body.get("policies"), dict) else {},
                "turns": turns,
                "max_steps": 25,
                "max_tool_calls": 50,
                "budget_micro_usd": 1_000_000_000,
            },
            {"configurable": {"thread_id": str(run.id)}},
        )
    except BusinessFailure:
        raise
    except (ConnectionError, TimeoutError, OSError) as exc:
        raise InfrastructureFailure("run execution failed") from exc
    if result.get("status") == "failed":
        run.status = "failed"
        run.error_code = str(result.get("error_code") or "run_failed")
        run.error_message = str(result.get("final_text") or "") or None
        run.finished_at = datetime.now(UTC)
        await append_outbox(
            session,
            workspace_id=run.workspace_id,
            topic="events",
            payload={"type": "run.failed", "run_id": str(run.id), "code": run.error_code},
        )
        return
    run.status = "succeeded"
    run.finished_at = datetime.now(UTC)
    await append_outbox(
        session,
        workspace_id=run.workspace_id,
        topic="events",
        payload={"type": "run.succeeded", "run_id": str(run.id)},
    )


async def handle_outbox_drain(body: dict[str, Any], settings: Settings) -> dict[str, object]:
    workspace_id = _uuid(body.get("workspace_id"), "workspace_id")
    async with system_session(workspace_id) as session:
        result = await drain_outbox(session, get_publisher(settings))
    if result["retryable"]:
        raise InfrastructureFailure("publisher unavailable")
    return {"status": "drained", "published": result["published"]}


async def handle_gcs_upload(body: dict[str, Any], settings: Settings) -> dict[str, object]:
    return await handle_artifact_scan(gcs_push_body(body), settings)


async def handle_artifact_scan(body: dict[str, Any], settings: Settings) -> dict[str, object]:
    version_id = _uuid(body.get("version_id"), "version_id")
    workspace_id = _uuid(body.get("workspace_id"), "workspace_id")
    async with system_session(workspace_id) as session:
        version = (
            await session.execute(select(ArtifactVersion).where(ArtifactVersion.id == version_id))
        ).scalar_one_or_none()
        if version is None:
            raise BusinessFailure("not_found", "Artifact version does not exist.")
        if version.status not in {"pending", "scanning"}:
            return {"status": "already_claimed", "artifact_status": version.status}
        if version.status == "pending" and not await claim_scan(session, version_id):
            return {"status": "already_claimed"}
        await session.refresh(version)
        artifact = (
            await session.execute(select(Artifact).where(Artifact.id == version.artifact_id))
        ).scalar_one_or_none()
        if artifact is None:
            raise BusinessFailure("not_found", "Artifact does not exist.")
        data = _payload_bytes(body, version)
        scanned = None
        if settings.scanner_url:
            from younique.artifacts.scan import ScanResult

            parsed = await remote_scan(settings, data, artifact.name, version.declared_mime)
            signature = parsed.get("signature")
            detected = parsed.get("detected_mime")
            scanned = ScanResult(
                status=str(parsed.get("status") or "failed"),
                signature=signature if isinstance(signature, str) else None,
                detected_mime=detected if isinstance(detected, str) else None,
            )
        updated = await apply_bytes(
            session,
            _system(workspace_id),
            artifact,
            version,
            data,
            settings=settings,
            timeout_s=float(body.get("timeout_s") or 60),
            scanned=scanned,
        )
        return {"status": updated.status, "artifact_id": str(updated.artifact_id)}
    raise InfrastructureFailure("workspace session did not open")


def _payload_bytes(body: dict[str, Any], version: ArtifactVersion) -> bytes:
    raw = body.get("data_base64")
    if isinstance(raw, str):
        return base64.b64decode(raw)
    from younique.artifacts.store import get_store

    try:
        return get_store().get(version.gcs_bucket, version.gcs_object)
    except KeyError as exc:
        raise BusinessFailure("artifact_scan_failed", "Staged object is missing.") from exc


async def remote_scan(
    settings: Settings, data: bytes, name: str, declared: str
) -> dict[str, object]:
    if not settings.scanner_url:
        raise InfrastructureFailure("scanner url is not configured")
    try:
        async with httpx.AsyncClient(timeout=60) as client:
            response = await client.post(
                settings.scanner_url,
                content=data,
                headers={"x-filename": name, "x-declared-mime": declared},
            )
    except httpx.HTTPError as exc:
        raise InfrastructureFailure("scanner unavailable") from exc
    if response.status_code >= 500:
        raise InfrastructureFailure("scanner unavailable")
    parsed = response.json()
    if not isinstance(parsed, dict):
        raise BusinessFailure("artifact_scan_failed", "Scanner returned a malformed body.")
    return parsed
