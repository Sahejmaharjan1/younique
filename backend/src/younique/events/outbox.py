from __future__ import annotations

from datetime import UTC, datetime
from typing import Protocol
from uuid import UUID

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from younique.core.config import Settings
from younique.models import Outbox


class PublishError(Exception):
    def __init__(self, detail: str, *, retryable: bool) -> None:
        self.detail = detail
        self.retryable = retryable
        super().__init__(detail)


class EventPublisher(Protocol):
    async def publish(self, topic: str, payload: dict[str, object]) -> None: ...


class MemoryPublisher:
    def __init__(self) -> None:
        self.sent: list[tuple[str, dict[str, object]]] = []

    async def publish(self, topic: str, payload: dict[str, object]) -> None:
        self.sent.append((topic, dict(payload)))


class HttpPublisher:
    def __init__(self, url: str) -> None:
        self.url = url

    async def publish(self, topic: str, payload: dict[str, object]) -> None:
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                response = await client.post(self.url, json={"topic": topic, "payload": payload})
        except httpx.HTTPError as exc:
            raise PublishError("pubsub unavailable", retryable=True) from exc
        if response.status_code >= 500:
            raise PublishError("pubsub unavailable", retryable=True)
        if response.status_code >= 400:
            raise PublishError("pubsub rejected the event", retryable=False)


_memory = MemoryPublisher()


def get_publisher(settings: Settings) -> EventPublisher:
    if settings.pubsub_url:
        return HttpPublisher(settings.pubsub_url)
    return _memory


def get_memory_publisher() -> MemoryPublisher:
    return _memory


async def append_outbox(
    session: AsyncSession,
    *,
    workspace_id: UUID | None,
    topic: str,
    payload: dict[str, object],
) -> Outbox:
    row = Outbox(workspace_id=workspace_id, topic=topic, payload=payload)
    session.add(row)
    await session.flush()
    return row


async def drain_outbox(
    session: AsyncSession, publisher: EventPublisher, *, limit: int = 50
) -> dict[str, int]:
    rows = (
        (
            await session.execute(
                select(Outbox)
                .where(Outbox.published_at.is_(None))
                .order_by(Outbox.created_at)
                .limit(limit)
                .with_for_update(skip_locked=True)
            )
        )
        .scalars()
        .all()
    )
    published = 0
    retryable = 0
    now = datetime.now(UTC)
    for row in rows:
        try:
            await publisher.publish(row.topic, dict(row.payload))
        except PublishError as exc:
            row.attempts += 1
            row.last_error = exc.detail[:500]
            if exc.retryable and row.attempts < 8:
                retryable += 1
            else:
                row.published_at = now
        else:
            row.published_at = now
            row.last_error = None
            published += 1
    return {"published": published, "retryable": retryable}
