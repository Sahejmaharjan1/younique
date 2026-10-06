from __future__ import annotations

import json
import uuid
from collections.abc import AsyncIterator, Awaitable, Callable
from datetime import UTC
from typing import Any
from uuid import UUID

from fastapi import Depends, FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse, Response, StreamingResponse
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from younique.authz.policy import decide
from younique.authz.principal import Principal, ResourceView
from younique.core.config import Settings, get_settings
from younique.core.db import apply_tenant, get_sessionmaker
from younique.core.errors import (
    ProblemDetail,
    consent_required,
    csrf_failed,
    not_found,
    permission_denied,
    problem,
)
from younique.core.firebase import verify_id_token
from younique.core.logging import configure_logging
from younique.core.otel import configure_otel
from younique.core.rate_limit import hit
from younique.core.redact import redact_value
from younique.core.security import clear_session_cookie, csrf_cookie, session_cookie, sha256_hex
from younique.llm.types import PriceSnapshot
from younique.models import (
    Approval,
    Artifact,
    ArtifactVersion,
    Connection,
    IdempotencyKey,
    Message,
    ModelProvider,
    ProviderKey,
    Session,
    ToolPolicy,
)
from younique.services.accounts import (
    exchange_session,
    list_accounts,
    missing_consents,
    resolve_principal,
)
from younique.services.artifacts_flow import (
    accept_upload,
    artifact_detail,
    list_artifacts,
    preview_payload,
    reserve_upload,
)
from younique.services.product import (
    archive_chat,
    bundle_tools,
    catalogue,
    connect_smtp,
    create_chat,
    create_share,
    decide_approval,
    download_version,
    get_chat,
    ingest_upload,
    list_chats,
    list_message_views,
    list_models,
    provider_key_view,
    record_usage,
    replay_events,
    resolve_share,
    revoke_provider_key,
    revoke_share,
    rotate_provider_key,
    save_provider_key,
    send_message,
    sse,
    update_chat,
    user_text_before,
    write_audit,
)

CSRF_EXEMPT = {"/v1/auth/session", "/healthz", "/readyz"}
CONSENT_EXEMPT_PREFIXES = ("/v1/me", "/v1/auth", "/healthz", "/readyz", "/v1/public", "/internal")


def public(fn: Callable[..., Any]) -> Callable[..., Any]:
    fn.__public__ = True  # type: ignore[attr-defined]
    return fn


class SessionIn(BaseModel):
    id_token: str
    step_up: bool = False


class ChatIn(BaseModel):
    title: str = "New chat"
    model_id: UUID | None = None


class MessageIn(BaseModel):
    text: str
    turns: list[dict[str, Any]] | None = None


class KeyIn(BaseModel):
    provider: str
    label: str
    secret: str
    base_url: str | None = None


class DecisionIn(BaseModel):
    decision: str
    remember: str | None = None
    note: str | None = None


class ShareIn(BaseModel):
    password: str | None = None
    include_reasoning: bool = False


class SmtpIn(BaseModel):
    host: str
    port: int = 587
    username: str
    password: str


class ConsentIn(BaseModel):
    document_id: UUID


class PolicyIn(BaseModel):
    tool_key: str
    mode: str
    allow_when_tainted: bool = False


class ChatPatch(BaseModel):
    title: str | None = None
    reasoning_mode: str | None = None


class RegenerateIn(BaseModel):
    message_id: UUID


class RotateIn(BaseModel):
    secret: str


def create_app(settings: Settings | None = None) -> FastAPI:
    cfg = settings or get_settings()
    configure_logging()
    configure_otel(cfg.otel_enabled)
    app = FastAPI(title="Younique", version="0.1.0")
    app.state.settings = cfg

    @app.middleware("http")
    async def request_context(
        request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        request_id = request.headers.get("x-request-id") or str(uuid.uuid4())
        request.state.request_id = request_id
        body = await request.body()
        request.state.cached_body = body

        async def receive() -> dict[str, Any]:
            return {"type": "http.request", "body": body, "more_body": False}

        request = Request(request.scope, receive)
        request.state.request_id = request_id
        request.state.cached_body = body
        if (
            request.method in {"POST", "PUT", "PATCH", "DELETE"}
            and request.url.path not in CSRF_EXEMPT
            and not request.url.path.startswith("/internal")
            and not request.url.path.startswith("/v1/public")
        ):
            cookies = _cookies(request.headers.get("cookie"))
            if cookies.get("csrf") and request.headers.get("x-csrf-token") != cookies.get("csrf"):
                return _problem_response(csrf_failed(), request_id)
            if "csrf" in cookies and request.headers.get("x-csrf-token") != cookies.get("csrf"):
                return _problem_response(csrf_failed(), request_id)
        try:
            ip = request.client.host if request.client else "0.0.0.0"
            remaining, reset = hit(f"ip:{ip}", limit=cfg.rate_limit_per_minute)
        except ProblemDetail as exc:
            denied: Response = _problem_response(exc, request_id)
            return denied
        response = await call_next(request)
        response.headers["X-Request-Id"] = request_id
        response.headers["RateLimit-Limit"] = str(cfg.rate_limit_per_minute)
        response.headers["RateLimit-Remaining"] = str(remaining)
        response.headers["RateLimit-Reset"] = str(reset)
        return response

    @app.exception_handler(ProblemDetail)
    async def problem_handler(request: Request, exc: ProblemDetail) -> JSONResponse:
        request_id = getattr(request.state, "request_id", "")
        return _problem_response(exc, request_id)

    @app.exception_handler(RequestValidationError)
    async def validation_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
        request_id = getattr(request.state, "request_id", "")
        errors = [
            {
                "field": ".".join(str(part) for part in item["loc"]),
                "code": "invalid",
                "detail": item["msg"],
            }
            for item in exc.errors()
        ]
        return _problem_response(
            problem(422, "validation_failed", "Validation failed", errors=errors), request_id
        )

    @app.get("/healthz")
    @public
    async def healthz() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/readyz")
    @public
    async def readyz() -> dict[str, str]:
        return {"status": "ready"}

    @app.post("/v1/auth/session")
    @public
    async def login(payload: SessionIn, request: Request) -> JSONResponse:
        claims = await verify_id_token(payload.id_token, cfg)
        cookies = _cookies(request.headers.get("cookie"))
        async with get_sessionmaker()() as db, db.begin():
            issued = await exchange_session(
                db,
                claims=claims,
                settings=cfg,
                user_agent=request.headers.get("user-agent", ""),
                ip=request.client.host if request.client else None,
                existing_token=cookies.get("__Host-session") or cookies.get("session"),
                step_up=payload.step_up,
            )
            body = {
                "user": {
                    "id": str(issued.user.id),
                    "email": issued.user.primary_email,
                    "display_name": issued.user.display_name,
                },
                "workspace": {"id": str(issued.workspace.id), "name": issued.workspace.name},
                "account_id": str(issued.user.id),
                "consent_required": issued.consent_required,
            }
        response = JSONResponse(body)
        response.headers.append(
            "set-cookie", session_cookie(issued.token, secure=cfg.cookie_secure)
        )
        response.headers.append("set-cookie", csrf_cookie(issued.csrf, secure=cfg.cookie_secure))
        response.headers["X-Request-Id"] = request.state.request_id
        return response

    @app.delete("/v1/auth/session")
    async def logout(
        principal: Principal = Depends(authorize("read", "session")),
        db: AsyncSession = Depends(db_session),
    ) -> Response:
        row = (
            await db.execute(select(Session).where(Session.id == principal.session_id))
        ).scalar_one()
        from datetime import datetime

        row.revoked_at = datetime.now(UTC)
        row.revoked_reason = "logout"
        response = Response(status_code=204)
        response.headers.append("set-cookie", clear_session_cookie(secure=cfg.cookie_secure))
        return response

    @app.get("/v1/me")
    async def me(
        principal: Principal = Depends(authorize("read", "user")),
        db: AsyncSession = Depends(db_session),
    ) -> dict[str, object]:
        required = await missing_consents(db, principal.user_id) if principal.user_id else []
        return {
            "user_id": str(principal.user_id),
            "workspace_id": str(principal.workspace_id),
            "role": principal.workspace_role,
            "consent_required": required,
        }

    @app.get("/v1/me/consents")
    async def consents(
        principal: Principal = Depends(authorize("read", "user")),
        db: AsyncSession = Depends(db_session),
    ) -> dict[str, object]:
        required = await missing_consents(db, principal.user_id) if principal.user_id else []
        return {"required": required}

    @app.post("/v1/me/consents")
    async def accept_consent(
        payload: ConsentIn,
        principal: Principal = Depends(authorize("update", "user")),
        db: AsyncSession = Depends(db_session),
        request: Request = Depends(_request),
    ) -> dict[str, str]:
        from younique.models import ConsentAcceptance, ConsentDocument

        doc = (
            await db.execute(
                select(ConsentDocument).where(ConsentDocument.id == payload.document_id)
            )
        ).scalar_one_or_none()
        if doc is None:
            raise not_found()
        db.add(
            ConsentAcceptance(
                user_id=principal.user_id,
                consent_document_id=doc.id,
                ip=request.client.host if request.client else None,
                user_agent=request.headers.get("user-agent", ""),
                content_sha256=doc.content_sha256,
            )
        )
        return {"status": "accepted"}

    @app.get("/v1/me/sessions")
    async def sessions(
        principal: Principal = Depends(authorize("read", "session")),
        db: AsyncSession = Depends(db_session),
    ) -> dict[str, object]:
        rows = (
            (await db.execute(select(Session).where(Session.user_id == principal.user_id)))
            .scalars()
            .all()
        )
        return {
            "data": [
                {
                    "id": str(row.id),
                    "revoked_at": row.revoked_at,
                    "expires_at": row.expires_at,
                    "last_seen_at": row.last_seen_at,
                    "is_current": row.id == principal.session_id,
                }
                for row in rows
            ]
        }

    @app.post("/v1/me/sessions/{session_id}:revoke")
    async def revoke_session(
        session_id: UUID,
        principal: Principal = Depends(authorize("delete", "session")),
        db: AsyncSession = Depends(db_session),
    ) -> dict[str, str]:
        row = (
            await db.execute(
                select(Session).where(
                    Session.id == session_id, Session.user_id == principal.user_id
                )
            )
        ).scalar_one_or_none()
        if row is None:
            raise not_found()
        from datetime import datetime

        row.revoked_at = datetime.now(UTC)
        row.revoked_reason = "device_list"
        await write_audit(
            db,
            principal,
            action="session.revoke",
            resource_type="session",
            resource_id=row.id,
            outcome="allowed",
        )
        return {"status": "revoked"}

    @app.get("/v1/chats")
    async def chats(
        principal: Principal = Depends(authorize("list", "chat")),
        db: AsyncSession = Depends(db_session),
        archived: bool = False,
    ) -> dict[str, object]:
        rows = await list_chats(db, principal, archived)
        return {
            "data": [
                {"id": str(row.id), "title": row.title, "archived_at": row.archived_at}
                for row in rows
            ],
            "next_cursor": None,
        }

    @app.post("/v1/chats")
    async def post_chat(
        payload: ChatIn,
        principal: Principal = Depends(authorize("create", "chat")),
        db: AsyncSession = Depends(db_session),
    ) -> dict[str, str]:
        chat = await create_chat(db, principal, payload.title, payload.model_id)
        return {"id": str(chat.id), "title": chat.title}

    @app.delete("/v1/chats/{chat_id}")
    async def delete_chat(
        chat_id: UUID,
        principal: Principal = Depends(authorize("delete", "chat")),
        db: AsyncSession = Depends(db_session),
    ) -> Response:
        chat = await get_chat(db, chat_id)
        await archive_chat(db, chat, principal, False)
        return Response(status_code=204)

    @app.post("/v1/chats/{chat_id}:restore")
    async def restore_chat(
        chat_id: UUID,
        principal: Principal = Depends(authorize("update", "chat")),
        db: AsyncSession = Depends(db_session),
    ) -> dict[str, str]:
        chat = await get_chat(db, chat_id)
        await archive_chat(db, chat, principal, True)
        return {"id": str(chat.id), "status": "active"}

    @app.post("/v1/chats/{chat_id}/messages")
    async def post_message(
        chat_id: UUID,
        payload: MessageIn,
        request: Request,
        principal: Principal = Depends(authorize("run", "chat")),
        db: AsyncSession = Depends(db_session),
    ) -> Response:
        await _require_consent(request, principal, db)
        chat = await get_chat(db, chat_id)
        turns = payload.turns if cfg.llm_mode == "fake" else None

        async def generate() -> AsyncIterator[str]:
            async for chunk in send_message(
                db, principal, chat, payload.text, settings=cfg, turns=turns
            ):
                yield chunk

        if request.headers.get("accept") == "text/event-stream":
            return StreamingResponse(generate(), media_type="text/event-stream")
        chunks = [chunk async for chunk in generate()]
        return Response("".join(chunks), media_type="text/event-stream")

    @app.get("/v1/chats/{chat_id}/messages")
    async def chat_messages(
        chat_id: UUID,
        principal: Principal = Depends(authorize("read", "chat")),
        db: AsyncSession = Depends(db_session),
    ) -> dict[str, object]:
        del principal
        await get_chat(db, chat_id)
        return {"data": await list_message_views(db, chat_id)}

    @app.get("/v1/chats/{chat_id}/artifacts")
    async def chat_artifacts(
        chat_id: UUID,
        principal: Principal = Depends(authorize("read", "chat")),
        db: AsyncSession = Depends(db_session),
    ) -> dict[str, object]:
        await get_chat(db, chat_id)
        return {"data": await list_artifacts(db, principal, chat_id=chat_id)}

    @app.patch("/v1/chats/{chat_id}")
    async def patch_chat(
        chat_id: UUID,
        payload: ChatPatch,
        principal: Principal = Depends(authorize("update", "chat")),
        db: AsyncSession = Depends(db_session),
    ) -> dict[str, object]:
        chat = await get_chat(db, chat_id)
        await update_chat(db, chat, title=payload.title, reasoning_mode=payload.reasoning_mode)
        return {"id": str(chat.id), "title": chat.title, "reasoning_mode": chat.reasoning_mode}

    @app.post("/v1/chats/{chat_id}/messages:regenerate")
    async def regenerate(
        chat_id: UUID,
        payload: RegenerateIn,
        request: Request,
        principal: Principal = Depends(authorize("run", "chat")),
        db: AsyncSession = Depends(db_session),
    ) -> Response:
        await _require_consent(request, principal, db)
        chat = await get_chat(db, chat_id)
        message = (
            await db.execute(
                select(Message).where(Message.id == payload.message_id, Message.chat_id == chat.id)
            )
        ).scalar_one_or_none()
        if message is None or message.role != "assistant":
            raise not_found()
        from datetime import datetime

        message.archived_at = datetime.now(UTC)
        text = await user_text_before(db, chat.id, message.seq)

        async def generate() -> AsyncIterator[str]:
            async for chunk in send_message(
                db, principal, chat, text, settings=cfg, turns=None, record_user=False
            ):
                yield chunk

        return StreamingResponse(generate(), media_type="text/event-stream")

    @app.post("/v1/share-links/{link_id}:revoke")
    async def revoke_link(
        link_id: UUID,
        principal: Principal = Depends(authorize("share", "chat")),
        db: AsyncSession = Depends(db_session),
    ) -> dict[str, str]:
        await revoke_share(db, principal, link_id)
        return {"status": "revoked"}

    @app.get("/v1/dev/mailbox")
    @public
    async def mailbox() -> dict[str, object]:
        if cfg.llm_mode != "fake" or cfg.app_env not in {"local", "test", "e2e"}:
            raise not_found()
        from younique.services.mailbox import snapshot

        return {"data": snapshot()}

    @app.get("/v1/runs/{run_id}/events")
    async def events(
        run_id: UUID,
        last_event_id: int = 0,
        principal: Principal = Depends(authorize("read", "run")),
        db: AsyncSession = Depends(db_session),
    ) -> Response:
        rows = await replay_events(db, run_id, last_event_id)

        async def generate() -> AsyncIterator[str]:
            for row in rows:
                yield sse(row.event_type, dict(row.data), row.seq)

        return StreamingResponse(generate(), media_type="text/event-stream")

    @app.post("/v1/runs/{run_id}:cancel")
    async def cancel(
        run_id: UUID,
        principal: Principal = Depends(authorize("update", "run")),
        db: AsyncSession = Depends(db_session),
    ) -> dict[str, str]:
        from younique.models import Run
        from younique.services.cancellation import mark

        mark(str(run_id))
        run = (await db.execute(select(Run).where(Run.id == run_id))).scalar_one_or_none()
        if run is None:
            return {"status": "cancelled"}
        run.status = "cancelled"
        run.error_code = "run_cancelled"
        streaming = (
            (
                await db.execute(
                    select(Message).where(Message.run_id == run.id, Message.status == "streaming")
                )
            )
            .scalars()
            .all()
        )
        for message in streaming:
            message.status = "stopped"
        return {"status": "cancelled"}

    @app.get("/v1/approvals")
    async def approvals(
        principal: Principal = Depends(authorize("list", "approval")),
        db: AsyncSession = Depends(db_session),
        status: str = "pending",
    ) -> dict[str, object]:
        rows = (
            (
                await db.execute(
                    select(Approval).where(
                        Approval.workspace_id == principal.workspace_id, Approval.status == status
                    )
                )
            )
            .scalars()
            .all()
        )
        return {
            "data": [
                {
                    "id": str(row.id),
                    "tool_key": row.tool_key,
                    "status": row.status,
                    "summary": row.summary,
                }
                for row in rows
            ]
        }

    @app.post("/v1/approvals/{approval_id}:decide")
    async def decide(
        approval_id: UUID,
        payload: DecisionIn,
        principal: Principal = Depends(authorize("decide_approval", "approval")),
        db: AsyncSession = Depends(db_session),
    ) -> dict[str, str]:
        row = await decide_approval(
            db, principal, approval_id, payload.decision, payload.remember, cfg
        )
        return {"id": str(row.id), "status": row.status}

    @app.get("/v1/tool-policies")
    async def get_policies(
        principal: Principal = Depends(authorize("read", "tool_policy")),
        db: AsyncSession = Depends(db_session),
    ) -> dict[str, object]:
        rows = (
            (
                await db.execute(
                    select(ToolPolicy).where(ToolPolicy.workspace_id == principal.workspace_id)
                )
            )
            .scalars()
            .all()
        )
        return {
            "data": [
                {
                    "id": str(row.id),
                    "tool_key": row.tool_key,
                    "mode": row.mode,
                    "allow_when_tainted": row.allow_when_tainted,
                    "risk": row.risk,
                }
                for row in rows
            ]
        }

    @app.put("/v1/tool-policies")
    async def put_policy(
        payload: PolicyIn,
        principal: Principal = Depends(authorize("update", "tool_policy")),
        db: AsyncSession = Depends(db_session),
    ) -> dict[str, str]:
        if payload.mode == "always_allow":
            from younique.services.accounts import fresh_reauth

            if not fresh_reauth(principal, cfg):
                from younique.core.errors import reauth_required

                raise reauth_required()
        row = (
            await db.execute(
                select(ToolPolicy).where(
                    ToolPolicy.workspace_id == principal.workspace_id,
                    ToolPolicy.tool_key == payload.tool_key,
                )
            )
        ).scalar_one_or_none()
        if row is None:
            row = ToolPolicy(
                workspace_id=principal.workspace_id,
                tool_key=payload.tool_key,
                mode=payload.mode,
                allow_when_tainted=payload.allow_when_tainted,
                risk="high",
            )
            db.add(row)
        else:
            row.mode = payload.mode
            row.allow_when_tainted = payload.allow_when_tainted
        return {"status": "saved"}

    @app.get("/v1/models")
    async def models(
        principal: Principal = Depends(authorize("list", "model")),
        db: AsyncSession = Depends(db_session),
        available: bool = False,
    ) -> dict[str, object]:
        rows = await list_models(db, principal, available)
        return {
            "data": [
                {
                    "id": str(row.id),
                    "model_ref": row.model_ref,
                    "display_name": row.display_name,
                    "supports_tools": row.supports_tools,
                    "supports_reasoning": row.supports_reasoning,
                }
                for row in rows
            ]
        }

    @app.get("/v1/provider-keys")
    async def keys(
        principal: Principal = Depends(authorize("list", "provider_key")),
        db: AsyncSession = Depends(db_session),
    ) -> dict[str, object]:
        rows = (
            (
                await db.execute(
                    select(ProviderKey).where(ProviderKey.workspace_id == principal.workspace_id)
                )
            )
            .scalars()
            .all()
        )
        data = []
        for row in rows:
            provider = (
                await db.execute(select(ModelProvider).where(ModelProvider.id == row.provider_id))
            ).scalar_one()
            data.append(provider_key_view(row, provider.key))
        return {"data": data}

    @app.post("/v1/provider-keys")
    async def post_key(
        payload: KeyIn,
        principal: Principal = Depends(authorize("create", "provider_key")),
        db: AsyncSession = Depends(db_session),
    ) -> dict[str, object]:
        row = await save_provider_key(
            db,
            principal,
            provider_key=payload.provider,
            label=payload.label,
            secret=payload.secret,
            settings=cfg,
            base_url=payload.base_url,
        )
        provider = (
            await db.execute(select(ModelProvider).where(ModelProvider.id == row.provider_id))
        ).scalar_one()
        return provider_key_view(row, provider.key)

    @app.post("/v1/provider-keys/{key_id}:rotate")
    async def rotate_key(
        key_id: UUID,
        payload: RotateIn,
        principal: Principal = Depends(authorize("update", "provider_key")),
        db: AsyncSession = Depends(db_session),
    ) -> dict[str, object]:
        row = await rotate_provider_key(db, principal, key_id, payload.secret, cfg)
        provider = (
            await db.execute(select(ModelProvider).where(ModelProvider.id == row.provider_id))
        ).scalar_one()
        return provider_key_view(row, provider.key)

    @app.post("/v1/provider-keys/{key_id}:revoke")
    async def revoke_key(
        key_id: UUID,
        principal: Principal = Depends(authorize("delete", "provider_key")),
        db: AsyncSession = Depends(db_session),
    ) -> dict[str, object]:
        row = await revoke_provider_key(db, principal, key_id)
        provider = (
            await db.execute(select(ModelProvider).where(ModelProvider.id == row.provider_id))
        ).scalar_one()
        return provider_key_view(row, provider.key)

    @app.get("/v1/auth/accounts")
    async def accounts(
        principal: Principal = Depends(authorize("read", "session")),
        db: AsyncSession = Depends(db_session),
    ) -> dict[str, object]:
        return {"data": await list_accounts(db, principal)}

    @app.get("/v1/connectors")
    async def connectors(
        principal: Principal = Depends(authorize("list", "connection")),
    ) -> dict[str, object]:
        return {"data": catalogue()}

    @app.get("/v1/connections")
    async def connection_list(
        principal: Principal = Depends(authorize("list", "connection")),
        db: AsyncSession = Depends(db_session),
    ) -> dict[str, object]:
        rows = (
            (
                await db.execute(
                    select(Connection).where(Connection.workspace_id == principal.workspace_id)
                )
            )
            .scalars()
            .all()
        )
        return {
            "data": [
                {"id": str(row.id), "connector_key": row.connector_key, "status": row.status}
                for row in rows
            ]
        }

    @app.post("/v1/connections/smtp")
    async def smtp(
        payload: SmtpIn,
        principal: Principal = Depends(authorize("create", "connection")),
        db: AsyncSession = Depends(db_session),
    ) -> dict[str, object]:
        row = await connect_smtp(
            db,
            principal,
            host=payload.host,
            port=payload.port,
            username=payload.username,
            password=payload.password,
            settings=cfg,
        )
        return {
            "id": str(row.id),
            "connector_key": row.connector_key,
            "enabled_bundles": row.enabled_bundles,
            "tools": bundle_tools("smtp", set(row.enabled_bundles)),
        }

    @app.get("/v1/artifacts")
    async def artifacts(
        principal: Principal = Depends(authorize("list", "artifact")),
        db: AsyncSession = Depends(db_session),
        chat_id: UUID | None = None,
        status: str | None = None,
        origin: str | None = None,
    ) -> dict[str, object]:
        return {
            "data": await list_artifacts(
                db, principal, chat_id=chat_id, status=status, origin=origin
            )
        }

    @app.post("/v1/artifacts")
    async def upload(
        request: Request,
        principal: Principal = Depends(authorize("create", "artifact")),
        db: AsyncSession = Depends(db_session),
    ) -> dict[str, object]:
        body = json.loads(request.state.cached_body or b"{}")
        raw = body.get("content_base64")
        chat_raw = body.get("chat_id")
        chat_id = UUID(str(chat_raw)) if chat_raw else None
        if isinstance(raw, str):
            import base64

            data = base64.b64decode(raw)
            version = await ingest_upload(
                db,
                principal,
                name=str(body.get("name") or "file"),
                declared_mime=str(body.get("declared_mime") or "application/octet-stream"),
                data=data,
                timeout_s=float(body.get("timeout_s") or 30),
                settings=cfg,
                chat_id=chat_id,
            )
            return {
                "artifact_id": str(version.artifact_id),
                "version_id": str(version.id),
                "status": version.status,
            }
        return await reserve_upload(
            db,
            principal,
            name=str(body.get("name") or "file"),
            declared_mime=str(body.get("declared_mime") or "application/octet-stream"),
            byte_size=int(body.get("byte_size") or 0),
            settings=cfg,
            chat_id=chat_id,
        )

    @app.put("/v1/artifacts/{artifact_id}/content")
    async def put_content(
        artifact_id: UUID,
        request: Request,
        principal: Principal = Depends(authorize("update", "artifact")),
        db: AsyncSession = Depends(db_session),
    ) -> dict[str, object]:
        data = request.state.cached_body or b""
        version = await accept_upload(
            db,
            principal,
            artifact_id,
            data,
            token=request.headers.get("x-upload-token") or "",
            settings=cfg,
            timeout_s=float(request.headers.get("x-scan-timeout") or 30),
        )
        return {
            "artifact_id": str(version.artifact_id),
            "version_id": str(version.id),
            "status": version.status,
            "detected_mime": version.detected_mime,
        }

    @app.get("/v1/artifacts/{artifact_id}")
    async def artifact(
        artifact_id: UUID,
        principal: Principal = Depends(authorize("read", "artifact")),
        db: AsyncSession = Depends(db_session),
    ) -> dict[str, object]:
        del principal
        return await artifact_detail(db, artifact_id)

    @app.get("/v1/artifacts/{artifact_id}/preview")
    async def artifact_preview(
        artifact_id: UUID,
        principal: Principal = Depends(authorize("read", "artifact")),
        db: AsyncSession = Depends(db_session),
    ) -> dict[str, object]:
        del principal
        return await preview_payload(db, artifact_id)

    @app.get("/v1/artifacts/{artifact_id}/download")
    async def download(
        artifact_id: UUID,
        principal: Principal = Depends(authorize("read", "artifact")),
        db: AsyncSession = Depends(db_session),
    ) -> dict[str, object]:
        artifact_row = (
            await db.execute(select(Artifact).where(Artifact.id == artifact_id))
        ).scalar_one_or_none()
        version = (
            (
                await db.execute(
                    select(ArtifactVersion)
                    .where(ArtifactVersion.artifact_id == artifact_id)
                    .order_by(ArtifactVersion.version.desc())
                )
            )
            .scalars()
            .first()
        )
        if version is None or artifact_row is None:
            raise not_found()
        payload = download_version(version, artifact_row.name)
        await write_audit(
            db,
            principal,
            action="artifact.download",
            resource_type="artifact",
            resource_id=artifact_id,
            outcome="allowed",
        )
        return payload

    @app.post("/v1/chats/{chat_id}/share-links")
    async def share(
        chat_id: UUID,
        payload: ShareIn,
        principal: Principal = Depends(authorize("share", "chat")),
        db: AsyncSession = Depends(db_session),
    ) -> dict[str, object]:
        await get_chat(db, chat_id)
        link, token = await create_share(
            db,
            principal,
            resource_type="chat",
            resource_id=chat_id,
            password=payload.password,
            include_reasoning=payload.include_reasoning,
        )
        return {"id": str(link.id), "token": token, "role": link.role}

    @app.get("/v1/public/{token}")
    @public
    async def public_share(token: str, password: str | None = None) -> JSONResponse:
        async with get_sessionmaker()() as db, db.begin():
            body = await resolve_share(db, token, password)
        response = JSONResponse(body)
        response.headers["X-Robots-Tag"] = "noindex, nofollow"
        return response

    @app.get("/v1/usage")
    async def usage(
        principal: Principal = Depends(authorize("read", "usage")),
        db: AsyncSession = Depends(db_session),
    ) -> dict[str, object]:
        from sqlalchemy import func

        from younique.models import UsageEvent

        total = (
            await db.execute(
                select(func.coalesce(func.sum(UsageEvent.cost_micro_usd), 0)).where(
                    UsageEvent.workspace_id == principal.workspace_id
                )
            )
        ).scalar_one()
        return {"cost_micro_usd": int(total)}

    @app.post("/v1/usage/events")
    async def post_usage(
        request: Request,
        principal: Principal = Depends(authorize("create", "usage")),
        db: AsyncSession = Depends(db_session),
    ) -> dict[str, object]:
        body = json.loads(request.state.cached_body or b"{}")
        price = PriceSnapshot(
            input_micro_usd_per_mtok=int(body["input_micro_usd_per_mtok"]),
            output_micro_usd_per_mtok=int(body["output_micro_usd_per_mtok"]),
            cached_input_micro_usd_per_mtok=int(body["cached_input_micro_usd_per_mtok"]),
            reasoning_micro_usd_per_mtok=int(body["reasoning_micro_usd_per_mtok"]),
        )
        event = await record_usage(
            db,
            principal,
            model_id=UUID(body["model_id"]) if body.get("model_id") else None,
            run_id=None,
            chat_id=None,
            input_tokens=int(body.get("input_tokens") or 0),
            cached_input_tokens=int(body.get("cached_input_tokens") or 0),
            output_tokens=int(body.get("output_tokens") or 0),
            reasoning_tokens=int(body.get("reasoning_tokens") or 0),
            price=price,
            request_id=str(body["request_id"]),
        )
        return {
            "recorded": event is not None,
            "cost_micro_usd": None if event is None else event.cost_micro_usd,
        }

    from younique.tasks.http import mount_worker_routes

    mount_worker_routes(app, cfg)
    return app


def authorize(action: str, resource_type: str) -> Callable[..., Any]:
    async def dependency(request: Request, db: AsyncSession = Depends(db_session)) -> Principal:
        principal = await _principal_from_request(request, db)
        request.state.principal = principal
        resource = ResourceView(
            type=resource_type,
            id=None,
            workspace_id=principal.workspace_id,
            owner_user_id=principal.user_id,
        )
        decision = decide(principal, _action_name(action), resource)
        if not decision.allowed:
            if decision.code == "not_found":
                raise not_found()
            raise permission_denied()
        if request.method in {"POST", "PUT", "PATCH"} and request.url.path not in CSRF_EXEMPT:
            await _idempotency(request, db, principal)
        return principal

    dependency.__authorize_action__ = action  # type: ignore[attr-defined]
    dependency.__authorize_resource__ = resource_type  # type: ignore[attr-defined]
    return dependency


def _action_name(action: str) -> str:
    mapping = {
        "list": "list",
        "read": "read",
        "create": "create",
        "update": "update",
        "delete": "delete",
        "share": "share",
        "run": "run",
        "decide_approval": "decide_approval",
    }
    return mapping.get(action, action)


async def db_session(request: Request) -> AsyncIterator[AsyncSession]:
    principal = getattr(request.state, "principal", None)
    maker = get_sessionmaker()
    async with maker() as session:
        async with session.begin():
            if isinstance(principal, Principal):
                await apply_tenant(
                    session, workspace_id=principal.workspace_id, user_id=principal.user_id
                )
            yield session


async def _principal_from_request(request: Request, db: AsyncSession) -> Principal:
    cookies = _cookies(request.headers.get("cookie"))
    token = cookies.get("__Host-session") or cookies.get("session")
    return await resolve_principal(
        db,
        token=token,
        account_id=request.headers.get("x-account-id"),
        workspace_header=request.headers.get("x-workspace-id"),
        settings=request.app.state.settings,
    )


async def _require_consent(request: Request, principal: Principal, db: AsyncSession) -> None:
    path = request.url.path
    if any(path.startswith(prefix) for prefix in CONSENT_EXEMPT_PREFIXES):
        return
    if principal.user_id is None:
        return
    required = await missing_consents(db, principal.user_id)
    if required:
        raise consent_required(required)


async def _idempotency(request: Request, db: AsyncSession, principal: Principal) -> None:
    if request.method != "POST":
        return
    key = request.headers.get("idempotency-key")
    if not key or principal.user_id is None or principal.workspace_id is None:
        return
    body = getattr(request.state, "cached_body", b"") or b""
    digest = sha256_hex(body.decode() if isinstance(body, bytes) else str(body))
    existing = (
        await db.execute(
            select(IdempotencyKey).where(
                IdempotencyKey.workspace_id == principal.workspace_id,
                IdempotencyKey.user_id == principal.user_id,
                IdempotencyKey.endpoint == request.url.path,
                IdempotencyKey.key == key,
            )
        )
    ).scalar_one_or_none()
    if existing and existing.request_sha256 != digest:
        raise problem(
            409,
            "idempotency_key_reuse",
            "Idempotency key reuse",
            "This key was used with a different body.",
        )
    if existing and existing.state == "completed" and existing.response_body is not None:
        raise _Replay(existing.response_status or 200, existing.response_body)
    if existing is None:
        from datetime import datetime, timedelta

        db.add(
            IdempotencyKey(
                workspace_id=principal.workspace_id,
                user_id=principal.user_id,
                key=key,
                endpoint=request.url.path,
                request_sha256=digest,
                state="in_flight",
                expires_at=datetime.now(UTC) + timedelta(hours=24),
            )
        )


class _Replay(Exception):
    def __init__(self, status: int, body: dict[str, object]) -> None:
        self.status = status
        self.body = body


def _cookies(header: str | None) -> dict[str, str]:
    found: dict[str, str] = {}
    if not header:
        return found
    for part in header.split(";"):
        if "=" not in part:
            continue
        name, value = part.split("=", 1)
        found[name.strip()] = value.strip()
    return found


def _problem_response(exc: ProblemDetail, request_id: str) -> JSONResponse:
    body = redact_value(exc.to_dict(request_id))
    return JSONResponse(body, status_code=exc.status, media_type="application/problem+json")


def _request(request: Request) -> Request:
    return request
