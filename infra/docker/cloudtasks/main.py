import os

import httpx
from fastapi import FastAPI, Request

app = FastAPI()
WORKER_URL = os.environ.get("WORKER_URL", "http://host.docker.internal:8001")


@app.get("/healthz")
async def healthz() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/v2/projects/{project}/locations/{location}/queues/{queue}/tasks")
async def create_task(request: Request) -> dict[str, str]:
    body = await request.json()
    task = body.get("task", body)
    http_request = task.get("httpRequest") or task.get("http_request") or {}
    url = http_request.get("url") or ""
    raw = http_request.get("body") or ""
    target = url or f"{WORKER_URL}/internal/tasks/dispatch"
    async with httpx.AsyncClient(timeout=30) as client:
        response = await client.post(target, content=raw.encode() if isinstance(raw, str) else raw)
    return {"status": "dispatched", "code": str(response.status_code)}
