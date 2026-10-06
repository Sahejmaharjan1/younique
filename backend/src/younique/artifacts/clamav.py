from __future__ import annotations

import asyncio
import struct

from younique.artifacts.scan import ScanResult


async def clam_scan(host: str, port: int, data: bytes, timeout_s: float = 60.0) -> ScanResult:
    try:
        reader, writer = await asyncio.wait_for(asyncio.open_connection(host, port), timeout_s)
    except (TimeoutError, OSError):
        return ScanResult(status="failed", signature="artifact_scan_failed")
    try:
        writer.write(b"zINSTREAM\0")
        view = memoryview(data)
        offset = 0
        while offset < len(view):
            chunk = view[offset : offset + 65536]
            writer.write(struct.pack(">I", len(chunk)))
            writer.write(chunk)
            offset += len(chunk)
        writer.write(struct.pack(">I", 0))
        await writer.drain()
        raw = await asyncio.wait_for(reader.read(4096), timeout_s)
    except (TimeoutError, OSError):
        return ScanResult(status="failed", signature="artifact_scan_failed")
    finally:
        writer.close()
        try:
            await writer.wait_closed()
        except OSError:
            pass
    text = raw.decode("utf-8", errors="replace")
    if "FOUND" in text:
        signature = text.split(":", 1)[-1].replace("FOUND", "").strip() or "FOUND"
        return ScanResult(status="infected", signature=signature)
    if text.strip().endswith("OK"):
        return ScanResult(status="clean")
    return ScanResult(status="failed", signature="artifact_scan_failed")
