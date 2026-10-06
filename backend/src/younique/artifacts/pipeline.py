from __future__ import annotations

import hashlib
from dataclasses import dataclass
from urllib.parse import quote

from younique.artifacts.preview import build_preview
from younique.artifacts.scan import ScanResult, scan_bytes
from younique.artifacts.store import ObjectStore
from younique.core.config import Settings


@dataclass(frozen=True)
class Placement:
    status: str
    bucket: str
    object_key: str
    detected_mime: str | None
    signature: str | None
    preview: dict[str, object] | None
    sha256: str


def place_upload(
    store: ObjectStore,
    *,
    data: bytes,
    name: str,
    declared_mime: str,
    workspace_id: str,
    artifact_id: str,
    uploads_bucket: str,
    artifacts_bucket: str,
    timeout_s: float = 30.0,
    scanned: ScanResult | None = None,
) -> Placement:
    digest = hashlib.sha256(data).hexdigest()
    staging_key = f"staging/{workspace_id}/{artifact_id}"
    store.put(uploads_bucket, staging_key, data)
    result = scanned or scan_bytes(
        data, declared_mime=declared_mime, name=name, timeout_s=timeout_s
    )
    if result.status == "clean":
        final_key = f"{workspace_id}/{artifact_id}"
        store.copy(uploads_bucket, staging_key, artifacts_bucket, final_key)
        store.delete(uploads_bucket, staging_key)
        preview = build_preview(data, result.detected_mime or declared_mime, name)
        return Placement(
            status="clean",
            bucket=artifacts_bucket,
            object_key=final_key,
            detected_mime=result.detected_mime,
            signature=None,
            preview=preview,
            sha256=digest,
        )
    if result.status == "infected":
        quarantine_key = f"quarantine/{workspace_id}/{artifact_id}"
        store.copy(uploads_bucket, staging_key, uploads_bucket, quarantine_key)
        store.delete(uploads_bucket, staging_key)
        return Placement(
            status="infected",
            bucket=uploads_bucket,
            object_key=quarantine_key,
            detected_mime=result.detected_mime,
            signature=result.signature,
            preview=None,
            sha256=digest,
        )
    store.delete(uploads_bucket, staging_key)
    return Placement(
        status="failed",
        bucket=uploads_bucket,
        object_key=staging_key,
        detected_mime=result.detected_mime,
        signature=result.signature,
        preview=None,
        sha256=digest,
    )


def resumable_upload_url(settings: Settings, bucket: str, object_name: str, byte_size: int) -> str:
    safe_name = quote(object_name, safe="")
    return (
        f"{settings.gcs_endpoint}/upload/storage/v1/b/{bucket}/o"
        f"?uploadType=resumable&name={safe_name}"
        f"&x-goog-content-length-range=0,{byte_size}"
    )


def content_disposition(name: str, mime: str | None) -> str:
    cleaned = name.replace('"', "").replace("\r", "").replace("\n", "") or "download"
    inline = {"image/png", "image/jpeg", "image/gif", "image/webp", "application/pdf"}
    kind = "inline" if mime in inline else "attachment"
    return f'{kind}; filename="{cleaned}"'
