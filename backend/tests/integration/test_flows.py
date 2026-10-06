from __future__ import annotations

import base64
import json
import os
import uuid
from urllib.parse import urlparse, urlunparse

import httpx
import pytest
from testcontainers.postgres import PostgresContainer

from younique.artifacts.scan import EICAR
from younique.core.db import reset_engine
from younique.core.rate_limit import reset_buckets


def _jwt(email: str) -> str:
    def segment(value: dict[str, object]) -> str:
        raw = json.dumps(value).encode()
        return base64.urlsafe_b64encode(raw).rstrip(b"=").decode()

    return (
        segment({"alg": "none", "typ": "JWT"})
        + "."
        + segment(
            {
                "sub": email,
                "email": email,
                "email_verified": True,
                "firebase": {"sign_in_provider": "password"},
            }
        )
        + ".sig"
    )


def _async_url(url: str) -> str:
    parsed = urlparse(url)
    return urlunparse(parsed._replace(scheme="postgresql+asyncpg"))


def _role(url: str, user: str, password: str) -> str:
    parsed = urlparse(_async_url(url))
    return urlunparse(parsed._replace(netloc=f"{user}:{password}@{parsed.hostname}:{parsed.port}"))


def _prepare(admin: str) -> str:
    app = _role(admin, "younique_app", "younique_app")
    os.environ["DATABASE_URL_MIGRATOR"] = admin
    os.environ["DATABASE_URL"] = app
    os.environ["FIREBASE_AUTH_EMULATOR_HOST"] = "localhost:9099"
    os.environ["COOKIE_SECURE"] = "false"
    os.environ["LLM_MODE"] = "fake"
    os.environ["OIDC_EMULATOR"] = "true"
    os.environ["APP_ENV"] = "test"
    reset_engine()
    from alembic import command
    from alembic.config import Config

    command.upgrade(Config("alembic.ini"), "head")
    return app


@pytest.fixture(scope="module")
def app_url() -> str:
    external = os.environ.get("YOUNIQUE_INTEGRATION_ADMIN_URL")
    if external:
        yield _prepare(_async_url(external))
        return
    with PostgresContainer("pgvector/pgvector:pg16") as postgres:
        yield _prepare(_async_url(postgres.get_connection_url()))


@pytest.mark.asyncio
async def test_mvp_flows_e1_to_e9(app_url: str) -> None:
    reset_buckets()
    reset_engine()
    from younique.api.factory import create_app
    from younique.core.config import Settings

    settings = Settings()
    application = create_app(settings)
    transport = httpx.ASGITransport(app=application)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        login = await client.post(
            "/v1/auth/session",
            json={"id_token": _jwt(f"{uuid.uuid4().hex[:8]}@example.com"), "step_up": True},
        )
        assert login.status_code == 200, login.text
        csrf = client.cookies.get("csrf")

        def headers() -> dict[str, str]:
            return {"x-csrf-token": csrf or "", "idempotency-key": str(uuid.uuid4())}

        me = await client.get("/v1/me")
        assert me.status_code == 200, me.text
        for item in me.json()["consent_required"]:
            accepted = await client.post(
                "/v1/me/consents", json={"document_id": item["id"]}, headers=headers()
            )
            assert accepted.status_code == 200, accepted.text
        saved = await client.post(
            "/v1/provider-keys",
            json={"provider": "fake", "label": "local", "secret": "valid-key"},
            headers=headers(),
        )
        assert saved.status_code == 200, saved.text
        assert "valid-key" not in saved.text
        assert saved.json()["last4"] == "valid-key"[-4:]
        chat = await client.post("/v1/chats", json={"title": "Hello"}, headers=headers())
        assert chat.status_code == 200, chat.text
        streamed = await client.post(
            f"/v1/chats/{chat.json()['id']}/messages",
            json={"text": "Hi", "turns": [{"text": "streamed hello", "tool_calls": []}]},
            headers={**headers(), "accept": "text/event-stream"},
        )
        assert streamed.status_code == 200, streamed.text
        assert "streamed hello" in streamed.text
        assert "run.completed" in streamed.text
        upload = await client.post(
            "/v1/artifacts",
            json={
                "name": "eicar.txt",
                "declared_mime": "text/plain",
                "content_base64": base64.b64encode(EICAR).decode(),
            },
            headers=headers(),
        )
        assert upload.status_code == 200, upload.text
        assert upload.json()["status"] == "infected"
        download = await client.get(f"/v1/artifacts/{upload.json()['artifact_id']}/download")
        assert download.status_code == 409
        assert download.json()["code"] == "artifact_not_clean"
        link = await client.post(
            f"/v1/chats/{chat.json()['id']}/share-links",
            json={"include_reasoning": False},
            headers=headers(),
        )
        assert link.status_code == 200, link.text
        public = await client.get(f"/v1/public/{link.json()['token']}")
        assert public.status_code == 200, public.text
        assert public.headers["x-robots-tag"] == "noindex, nofollow"
        assert "connections" in public.json()["excludes"]
        blocked = await client.put(
            "/v1/tool-policies",
            json={"tool_key": "smtp.send", "mode": "never", "allow_when_tainted": False},
            headers=headers(),
        )
        assert blocked.status_code == 200, blocked.text
        health = await client.get("/healthz")
        assert health.status_code == 200
