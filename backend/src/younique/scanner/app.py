from __future__ import annotations

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from younique.artifacts.clamav import clam_scan
from younique.artifacts.scan import ScanResult, scan_bytes
from younique.core.config import get_settings


def create_scanner_app() -> FastAPI:
    app = FastAPI(title="Younique Scanner")

    @app.get("/healthz")
    async def healthz() -> dict[str, str]:
        return {"status": "ok"}

    @app.post("/scan")
    async def scan(request: Request) -> JSONResponse:
        data = await request.body()
        name = request.headers.get("x-filename") or "upload.bin"
        declared = request.headers.get("x-declared-mime") or "application/octet-stream"
        timeout = float(request.headers.get("x-scan-timeout") or "60")
        result = await inspect_upload(data, name=name, declared_mime=declared, timeout_s=timeout)
        return JSONResponse(
            {
                "status": result.status,
                "signature": result.signature,
                "detected_mime": result.detected_mime,
            }
        )

    return app


async def inspect_upload(
    data: bytes, *, name: str, declared_mime: str, timeout_s: float
) -> ScanResult:
    typed = scan_bytes(data, declared_mime=declared_mime, name=name, timeout_s=timeout_s)
    settings = get_settings()
    if typed.status == "failed":
        return typed
    if settings.scanner_mode != "clamav":
        return typed
    clam = await clam_scan(settings.clamav_host, settings.clamav_port, data, timeout_s)
    if clam.status == "infected":
        return ScanResult(
            status="infected", signature=clam.signature, detected_mime=typed.detected_mime
        )
    if clam.status == "failed":
        return ScanResult(
            status="failed", signature="artifact_scan_failed", detected_mime=typed.detected_mime
        )
    return ScanResult(status="clean", detected_mime=typed.detected_mime)


app = create_scanner_app()
