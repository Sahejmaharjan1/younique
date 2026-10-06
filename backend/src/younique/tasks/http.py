from __future__ import annotations

import json
from collections.abc import Awaitable, Callable
from typing import Any

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from younique.core.config import Settings
from younique.core.errors import ProblemDetail
from younique.core.oidc import verify_internal_caller
from younique.tasks.handlers import (
    handle_agent_run,
    handle_artifact_scan,
    handle_gcs_upload,
    handle_outbox_drain,
    handle_pipeline_run,
)
from younique.tasks.outcomes import BusinessFailure, InfrastructureFailure

Handler = Callable[[dict[str, Any], Settings], Awaitable[dict[str, object]]]


def mount_worker_routes(app: FastAPI, cfg: Settings) -> None:
    async def guarded(request: Request, handler: Handler) -> JSONResponse:
        try:
            await verify_internal_caller(request.headers.get("authorization"), cfg)
            raw = await request.body()
            try:
                parsed: object = json.loads(raw or b"{}")
            except json.JSONDecodeError as exc:
                return JSONResponse(
                    {"status": "failed", "code": "validation_failed", "detail": str(exc)},
                    status_code=200,
                )
            body = parsed if isinstance(parsed, dict) else {}
            result = await handler(body, cfg)
        except BusinessFailure as exc:
            return JSONResponse(
                {"status": "failed", "code": exc.code, "detail": exc.detail}, status_code=200
            )
        except InfrastructureFailure:
            return JSONResponse({"status": "unavailable"}, status_code=503)
        except ProblemDetail as exc:
            return JSONResponse(exc.to_dict(""), status_code=exc.status)
        return JSONResponse(result, status_code=200)

    @app.post("/internal/tasks/agent-run")
    async def agent_run(request: Request) -> JSONResponse:
        return await guarded(request, handle_agent_run)

    @app.post("/internal/tasks/pipeline-run")
    async def pipeline_run(request: Request) -> JSONResponse:
        return await guarded(request, handle_pipeline_run)

    @app.post("/internal/tasks/artifact-scan")
    async def artifact_scan(request: Request) -> JSONResponse:
        return await guarded(request, handle_artifact_scan)

    @app.post("/internal/tasks/outbox-drain")
    async def outbox(request: Request) -> JSONResponse:
        return await guarded(request, handle_outbox_drain)

    @app.post("/internal/events/gcs-upload")
    async def gcs_upload(request: Request) -> JSONResponse:
        return await guarded(request, handle_gcs_upload)

    for route in app.routes:
        endpoint = getattr(route, "endpoint", None)
        if endpoint is not None and getattr(endpoint, "__public__", False) is False:
            path = getattr(route, "path", "")
            if isinstance(path, str) and path.startswith("/internal/"):
                endpoint.__public__ = True


def create_worker_app(settings: Settings | None = None) -> FastAPI:
    from younique.core.config import get_settings

    cfg = settings or get_settings()
    app = FastAPI(title="Younique Worker")
    app.state.settings = cfg

    @app.get("/healthz")
    async def healthz() -> dict[str, str]:
        return {"status": "ok"}

    mount_worker_routes(app, cfg)
    return app
