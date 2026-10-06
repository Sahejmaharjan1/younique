from __future__ import annotations

import json
from typing import Any

import httpx

from younique.core.config import Settings
from younique.tasks.outcomes import InfrastructureFailure


class TaskEnqueuer:
    def __init__(self) -> None:
        self.names: set[str] = set()
        self.pending: list[dict[str, object]] = []

    async def enqueue(
        self,
        *,
        queue: str,
        name: str,
        path: str,
        payload: dict[str, Any],
        settings: Settings,
    ) -> bool:
        if name in self.names:
            return False
        self.names.add(name)
        self.pending.append({"queue": queue, "name": name, "path": path, "payload": payload})
        if not settings.cloud_tasks_url:
            return True
        body = {"task": {"name": name, "httpRequest": {"url": path, "body": json.dumps(payload)}}}
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                response = await client.post(settings.cloud_tasks_url, json=body)
        except httpx.HTTPError as exc:
            self.names.discard(name)
            raise InfrastructureFailure("cloud tasks unavailable") from exc
        if response.status_code == 409:
            return False
        if response.status_code >= 500:
            self.names.discard(name)
            raise InfrastructureFailure("cloud tasks unavailable")
        return True


_enqueuer = TaskEnqueuer()


def get_enqueuer() -> TaskEnqueuer:
    return _enqueuer


def reset_enqueuer() -> None:
    global _enqueuer
    _enqueuer = TaskEnqueuer()
