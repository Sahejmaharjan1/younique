from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from younique.core.config import Settings, get_settings

_engine: AsyncEngine | None = None
_sessionmaker: async_sessionmaker[AsyncSession] | None = None


def reset_engine() -> None:
    global _engine, _sessionmaker
    _engine = None
    _sessionmaker = None


def get_engine(settings: Settings | None = None) -> AsyncEngine:
    global _engine, _sessionmaker
    if _engine is None:
        cfg = settings or get_settings()
        _engine = create_async_engine(cfg.database_url, pool_pre_ping=True)
        _sessionmaker = async_sessionmaker(_engine, expire_on_commit=False)
    return _engine


def get_sessionmaker(settings: Settings | None = None) -> async_sessionmaker[AsyncSession]:
    get_engine(settings)
    assert _sessionmaker is not None
    return _sessionmaker


async def set_local(session: AsyncSession, key: str, value: str | None) -> None:
    await session.execute(
        text("SELECT set_config(:key, :value, true)"),
        {"key": key, "value": "" if value is None else value},
    )


async def apply_tenant(
    session: AsyncSession,
    *,
    workspace_id: UUID | None,
    user_id: UUID | None,
    session_token_hash: str | None = None,
    bootstrap: bool = False,
) -> None:
    if session_token_hash is not None:
        await set_local(session, "app.session_token_hash", session_token_hash)
    if user_id is not None:
        await set_local(session, "app.user_id", str(user_id))
    if workspace_id is not None:
        await set_local(session, "app.workspace_id", str(workspace_id))
    await set_local(session, "app.bootstrap", "on" if bootstrap else "off")


@asynccontextmanager
async def system_session(
    workspace_id: UUID, user_id: UUID | None = None
) -> AsyncIterator[AsyncSession]:
    maker = get_sessionmaker()
    async with maker() as session, session.begin():
        await apply_tenant(session, workspace_id=workspace_id, user_id=user_id, bootstrap=True)
        yield session
