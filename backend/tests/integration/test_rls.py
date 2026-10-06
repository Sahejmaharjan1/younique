from __future__ import annotations

import os
import uuid
from urllib.parse import urlparse, urlunparse

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine
from testcontainers.postgres import PostgresContainer

from younique.core.db import apply_tenant, reset_engine
from younique.models.base import TENANT_TABLES


def _as_async(url: str) -> str:
    parsed = urlparse(url)
    scheme = "postgresql+asyncpg"
    return urlunparse(parsed._replace(scheme=scheme))


def _as_role(url: str, user: str, password: str) -> str:
    parsed = urlparse(_as_async(url))
    host = parsed.hostname or "localhost"
    port = parsed.port or 5432
    return urlunparse(parsed._replace(netloc=f"{user}:{password}@{host}:{port}"))


def _migrate(raw: str) -> None:
    os.environ["DATABASE_URL_MIGRATOR"] = raw
    os.environ["DATABASE_URL"] = _as_role(raw, "younique_app", "younique_app")
    reset_engine()
    from alembic import command
    from alembic.config import Config

    command.upgrade(Config("alembic.ini"), "head")


@pytest.fixture(scope="module")
def database_url() -> str:
    external = os.environ.get("YOUNIQUE_INTEGRATION_ADMIN_URL")
    if external:
        raw = _as_async(external)
        _migrate(raw)
        yield raw
        return
    with PostgresContainer("pgvector/pgvector:pg16") as postgres:
        raw = _as_async(postgres.get_connection_url())
        _migrate(raw)
        yield raw


@pytest.mark.asyncio
async def test_set_local_does_not_survive_commit(database_url: str) -> None:
    engine = create_async_engine(database_url)
    async with engine.connect() as conn:
        await conn.begin()
        await conn.execute(
            text("SELECT set_config('app.workspace_id', :v, true)"), {"v": str(uuid.uuid4())}
        )
        await conn.commit()
        value = (
            await conn.execute(text("SELECT current_setting('app.workspace_id', true)"))
        ).scalar()
        assert value in (None, "")
    await engine.dispose()


@pytest.mark.asyncio
async def test_app_role_has_no_bypass_and_sees_nothing(database_url: str) -> None:
    admin = create_async_engine(database_url)
    app_url = _as_role(database_url, "younique_app", "younique_app")
    async with admin.begin() as conn:
        flags = (
            await conn.execute(
                text("SELECT rolsuper, rolbypassrls FROM pg_roles WHERE rolname = 'younique_app'")
            )
        ).one()
        assert flags == (False, False)
        ws = uuid.uuid4()
        await conn.execute(
            text("INSERT INTO app.workspaces (id, slug, name) VALUES (:id, :slug, 'A')"),
            {"id": ws, "slug": f"iso-{ws.hex[:8]}"},
        )
        await conn.execute(
            text("INSERT INTO app.chats (id, workspace_id, title) VALUES (:id, :ws, 'secret')"),
            {"id": uuid.uuid4(), "ws": ws},
        )
    app = create_async_engine(app_url)
    async with app.connect() as conn:
        for table in TENANT_TABLES:
            if table == "workspaces":
                count = (await conn.execute(text("SELECT count(*) FROM app.workspaces"))).scalar()
            else:
                count = (await conn.execute(text(f"SELECT count(*) FROM app.{table}"))).scalar()
            assert count == 0, table
        await conn.rollback()
        async with conn.begin():
            await apply_tenant(conn, workspace_id=ws, user_id=None)
            visible = (await conn.execute(text("SELECT count(*) FROM app.chats"))).scalar()
            assert visible == 1
            other = uuid.uuid4()
            await apply_tenant(conn, workspace_id=other, user_id=None)
            hidden = (await conn.execute(text("SELECT count(*) FROM app.chats"))).scalar()
            assert hidden == 0
    await app.dispose()
    await admin.dispose()
