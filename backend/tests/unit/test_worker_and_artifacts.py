from __future__ import annotations

import httpx
import pytest

from younique.artifacts.pipeline import content_disposition, place_upload
from younique.artifacts.scan import EICAR, scan_bytes
from younique.artifacts.store import ObjectStore
from younique.core.config import Settings
from younique.scanner.app import create_scanner_app
from younique.services.product import download_version
from younique.tasks.enqueue import TaskEnqueuer
from younique.tasks.http import create_worker_app


def _png(width: int, height: int) -> bytes:
    signature = b"\x89PNG\r\n\x1a\n"
    ihdr = width.to_bytes(4, "big") + height.to_bytes(4, "big") + b"\x08\x02\x00\x00\x00"
    return signature + len(ihdr).to_bytes(4, "big") + b"IHDR" + ihdr


def test_magic_mismatch_depth_and_decompression_bomb() -> None:
    mismatch = scan_bytes(b"PK\x03\x04xxxx", declared_mime="application/pdf", name="report.pdf")
    assert mismatch.status == "failed"
    assert mismatch.signature == "extension_mismatch"
    nested = b"[" * 101 + b"]" * 101
    deep = scan_bytes(nested, declared_mime="application/json", name="deep.json")
    assert deep.signature == "json_depth"
    bomb = scan_bytes(_png(10000, 5001), declared_mime="image/png", name="big.png")
    assert bomb.signature == "decompression_bomb"
    denied = scan_bytes(b"MZ", declared_mime="application/octet-stream", name="run.exe")
    assert denied.signature == "unsupported_file_type"


def test_promotion_and_quarantine() -> None:
    store = ObjectStore()
    clean = place_upload(
        store,
        data=b"hello\n",
        name="note.txt",
        declared_mime="text/plain",
        workspace_id="ws",
        artifact_id="a1",
        uploads_bucket="uploads",
        artifacts_bucket="artifacts",
    )
    assert clean.status == "clean"
    assert clean.bucket == "artifacts"
    assert store.contains("artifacts", clean.object_key)
    assert not store.contains("uploads", "staging/ws/a1")
    assert clean.preview is not None
    assert clean.preview["kind"] == "text"
    infected = place_upload(
        store,
        data=EICAR,
        name="eicar.txt",
        declared_mime="text/plain",
        workspace_id="ws",
        artifact_id="a2",
        uploads_bucket="uploads",
        artifacts_bucket="artifacts",
    )
    assert infected.status == "infected"
    assert infected.object_key.startswith("quarantine/")
    assert store.contains("uploads", infected.object_key)
    assert "attachment" in content_disposition("eicar.txt", "text/plain")


def test_download_gate_blocks_non_clean() -> None:
    from uuid import UUID

    from younique.models import ArtifactVersion

    version = ArtifactVersion(
        workspace_id=UUID("00000000-0000-7000-8000-000000000099"),
        artifact_id=UUID("00000000-0000-7000-8000-000000000098"),
        version=1,
        gcs_bucket="uploads",
        gcs_object="quarantine/x",
        declared_mime="text/plain",
        byte_size=4,
        sha256="abc",
        status="infected",
    )
    from younique.core.errors import ProblemDetail

    with pytest.raises(ProblemDetail) as caught:
        download_version(version, "eicar.txt")
    assert caught.value.code == "artifact_not_clean"
    assert caught.value.status == 409


@pytest.mark.asyncio
async def test_scanner_quarantines_eicar() -> None:
    app = create_scanner_app()
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://scanner") as client:
        response = await client.post(
            "/scan",
            content=EICAR,
            headers={"x-filename": "eicar.txt", "x-declared-mime": "text/plain"},
        )
    assert response.status_code == 200
    assert response.json()["status"] == "infected"
    assert response.json()["signature"] == "EICAR-Test-Signature"


@pytest.mark.asyncio
async def test_named_tasks_dedup_and_business_failure_is_http_200() -> None:
    queue = TaskEnqueuer()
    settings = Settings(cloud_tasks_url="")
    first = await queue.enqueue(
        queue="agent-runs",
        name="run-1",
        path="/internal/tasks/agent-run",
        payload={"run_id": "1"},
        settings=settings,
    )
    second = await queue.enqueue(
        queue="agent-runs",
        name="run-1",
        path="/internal/tasks/agent-run",
        payload={"run_id": "1"},
        settings=settings,
    )
    assert first is True
    assert second is False
    app = create_worker_app(Settings(oidc_emulator=True, dev_internal_token="dev-internal"))
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://worker") as client:
        missing = await client.post("/internal/tasks/agent-run", json={})
        assert missing.status_code == 401
        failed = await client.post(
            "/internal/tasks/agent-run",
            json={},
            headers={"authorization": "Bearer dev-internal"},
        )
        assert failed.status_code == 200
        assert failed.json()["code"] == "validation_failed"
        drained = await client.post(
            "/internal/tasks/outbox-drain",
            json={},
            headers={"authorization": "Bearer dev-internal"},
        )
        assert drained.status_code == 200
        assert drained.json()["code"] == "validation_failed"
