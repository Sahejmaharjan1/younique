from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession

from younique.models import ArtifactVersion, Run


async def claim_run(session: AsyncSession, run_id: UUID) -> bool:
    result = await session.execute(
        update(Run)
        .where(Run.id == run_id, Run.status == "queued")
        .values(status="running", started_at=datetime.now(UTC))
        .returning(Run.id)
    )
    return result.scalar_one_or_none() is not None


async def claim_scan(session: AsyncSession, version_id: UUID) -> bool:
    result = await session.execute(
        update(ArtifactVersion)
        .where(ArtifactVersion.id == version_id, ArtifactVersion.status == "pending")
        .values(status="scanning")
        .returning(ArtifactVersion.id)
    )
    return result.scalar_one_or_none() is not None
