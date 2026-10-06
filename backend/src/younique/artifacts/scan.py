from __future__ import annotations

from dataclasses import dataclass

EICAR = b"X5O!P%@AP[4\\PZX54(P^)7CC)7}$EICAR-STANDARD-ANTIVIRUS-TEST-FILE!$H+H*"

MAGIC: tuple[tuple[bytes, str], ...] = (
    (b"%PDF", "application/pdf"),
    (b"\x89PNG\r\n\x1a\n", "image/png"),
    (b"\xff\xd8\xff", "image/jpeg"),
    (b"GIF87a", "image/gif"),
    (b"GIF89a", "image/gif"),
    (b"PK\x03\x04", "application/zip"),
)


@dataclass(frozen=True)
class ScanResult:
    status: str
    signature: str | None = None
    detected_mime: str | None = None


def detect_mime(data: bytes, declared: str) -> str:
    for signature, mime in MAGIC:
        if data.startswith(signature):
            return mime
    stripped = data.lstrip()
    if stripped.startswith(b"{") or stripped.startswith(b"["):
        return "application/json"
    if stripped.startswith(b"<svg") or stripped.startswith(b"<?xml"):
        return "image/svg+xml"
    return declared or "application/octet-stream"


def extension_matches(name: str, detected: str) -> bool:
    ext = name.rsplit(".", 1)[-1].lower() if "." in name else ""
    groups = {
        "pdf": "application/pdf",
        "png": "image/png",
        "jpg": "image/jpeg",
        "jpeg": "image/jpeg",
        "gif": "image/gif",
        "json": "application/json",
        "svg": "image/svg+xml",
        "csv": "text/csv",
        "txt": "text/plain",
        "zip": "application/zip",
    }
    expected = groups.get(ext)
    if expected is None:
        return True
    return expected == detected or detected == "application/octet-stream"


def scan_bytes(data: bytes, *, declared_mime: str, name: str, timeout_s: float = 30.0) -> ScanResult:
    if timeout_s <= 0:
        return ScanResult(status="failed", signature="timeout")
    detected = detect_mime(data, declared_mime)
    if not extension_matches(name, detected):
        return ScanResult(status="failed", signature="extension_mismatch", detected_mime=detected)
    if EICAR in data:
        return ScanResult(status="infected", signature="EICAR-Test-Signature", detected_mime=detected)
    return ScanResult(status="clean", detected_mime=detected)


def advance(status: str, result: ScanResult) -> str:
    if status not in {"pending", "scanning"}:
        return status
    if result.status == "clean":
        return "clean"
    if result.status == "infected":
        return "infected"
    return "failed"
