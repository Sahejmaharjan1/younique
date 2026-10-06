from __future__ import annotations

import json
from dataclasses import dataclass

EICAR = b"X5O!P%@AP[4\\PZX54(P^)7CC)7}$EICAR-STANDARD-ANTIVIRUS-TEST-FILE!$H+H*"
MAX_JSON_DEPTH = 100
MAX_PIXELS = 50_000_000

MAGIC: tuple[tuple[bytes, str], ...] = (
    (b"%PDF", "application/pdf"),
    (b"\x89PNG\r\n\x1a\n", "image/png"),
    (b"\xff\xd8\xff", "image/jpeg"),
    (b"GIF87a", "image/gif"),
    (b"GIF89a", "image/gif"),
    (b"PK\x03\x04", "application/zip"),
)

ALLOWED_MIME = {
    "text/plain",
    "text/csv",
    "text/tab-separated-values",
    "text/markdown",
    "text/html",
    "text/xml",
    "application/json",
    "application/pdf",
    "application/zip",
    "application/gzip",
    "application/xml",
    "image/png",
    "image/jpeg",
    "image/gif",
    "image/webp",
    "image/svg+xml",
}

DENIED_EXTENSIONS = {"exe", "dll", "so", "app", "lnk", "docm", "xlsm", "bat", "cmd", "scr", "msi"}


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


def _extension(name: str) -> str:
    return name.rsplit(".", 1)[-1].lower() if "." in name else ""


def extension_matches(name: str, detected: str) -> bool:
    ext = _extension(name)
    if ext in DENIED_EXTENSIONS:
        return False
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
        "md": "text/markdown",
        "html": "text/html",
        "htm": "text/html",
    }
    expected = groups.get(ext)
    if expected is None:
        return True
    return expected == detected or detected == "application/octet-stream"


def png_pixels(data: bytes) -> int | None:
    if not data.startswith(b"\x89PNG\r\n\x1a\n") or len(data) < 24:
        return None
    if data[12:16] != b"IHDR":
        return None
    width = int.from_bytes(data[16:20], "big")
    height = int.from_bytes(data[20:24], "big")
    return width * height


def json_too_deep(data: bytes, limit: int = MAX_JSON_DEPTH) -> bool:
    try:
        parsed: object = json.loads(data)
    except json.JSONDecodeError:
        return True
    stack: list[tuple[object, int]] = [(parsed, 1)]
    while stack:
        node, depth = stack.pop()
        if depth > limit:
            return True
        if isinstance(node, dict):
            stack.extend((value, depth + 1) for value in node.values())
        elif isinstance(node, list):
            stack.extend((value, depth + 1) for value in node)
    return False


def structural_problem(data: bytes, detected: str) -> str | None:
    if detected == "application/json" and json_too_deep(data):
        return "json_depth"
    if detected == "image/png":
        pixels = png_pixels(data)
        if pixels is not None and pixels > MAX_PIXELS:
            return "decompression_bomb"
    return None


def scan_bytes(
    data: bytes, *, declared_mime: str, name: str, timeout_s: float = 30.0
) -> ScanResult:
    if timeout_s <= 0:
        return ScanResult(status="failed", signature="timeout")
    detected = detect_mime(data, declared_mime)
    ext = _extension(name)
    if ext in DENIED_EXTENSIONS or detected not in ALLOWED_MIME:
        return ScanResult(
            status="failed", signature="unsupported_file_type", detected_mime=detected
        )
    if not extension_matches(name, detected):
        return ScanResult(status="failed", signature="extension_mismatch", detected_mime=detected)
    structural = structural_problem(data, detected)
    if structural is not None:
        return ScanResult(status="failed", signature=structural, detected_mime=detected)
    if EICAR in data:
        return ScanResult(
            status="infected", signature="EICAR-Test-Signature", detected_mime=detected
        )
    return ScanResult(status="clean", detected_mime=detected)


def advance(status: str, result: ScanResult) -> str:
    if status not in {"pending", "scanning"}:
        return status
    if result.status == "clean":
        return "clean"
    if result.status == "infected":
        return "infected"
    return "failed"
