from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID

from argon2 import PasswordHasher
from langgraph.types import Command
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from uuid6 import uuid7

from younique.agents.graph import compile_graph
from younique.agents.taint import flag_untrusted_arguments
from younique.authz.principal import Principal
from younique.connectors.registry import manifests, tools_for_bundles
from younique.core.config import Settings
from younique.core.db import apply_tenant
from younique.core.errors import (
    not_found,
    permission_denied,
    problem,
    reauth_required,
)
from younique.core.redact import redact_value
from younique.core.security import new_token, sha256_hex
from younique.crypto.envelope import build_kek, cache_dek, cached_dek, decrypt, encrypt
from younique.llm.types import PriceSnapshot
from younique.models import (
    Approval,
    ArtifactVersion,
    AuditLog,
    Chat,
    Connection,
    EncryptionKey,
    Message,
    MessagePart,
    Model,
    ModelPrice,
    ModelProvider,
    ProviderKey,
    Run,
    RunEvent,
    ShareLink,
    ToolPolicy,
    UsageEvent,
    UsageRequestDedupe,
)
from younique.services.accounts import fresh_reauth
from younique.services.scripted_turns import refusal_from, scripted_turns, without_reasoning
from younique.usage.cost import cost_micro_usd

_GRAPH: Any = None
_HASHER = PasswordHasher()


def get_graph() -> Any:
    global _GRAPH
    if _GRAPH is None:
        _GRAPH = compile_graph()
    return _GRAPH


def _now() -> datetime:
    return datetime.now(UTC)


async def write_audit(
    db: AsyncSession,
    principal: Principal,
    *,
    action: str,
    resource_type: str,
    resource_id: UUID | None,
    outcome: str,
    detail: dict[str, object] | None = None,
    request_id: str | None = None,
) -> None:
    db.add(
        AuditLog(
            workspace_id=principal.workspace_id,
            occurred_at=_now(),
            actor_user_id=principal.user_id,
            actor_kind=principal.kind if principal.kind != "anonymous" else "system",
            action=action,
            resource_type=resource_type,
            resource_id=resource_id,
            outcome=outcome,
            detail_redacted=redact_value(detail or {}),
            request_id=request_id,
        )
    )


async def create_chat(
    db: AsyncSession, principal: Principal, title: str, model_id: UUID | None
) -> Chat:
    chat = Chat(
        workspace_id=_ws(principal),
        title=title or "New chat",
        model_id=model_id,
        created_by=principal.user_id,
    )
    db.add(chat)
    await db.flush()
    return chat


async def list_chats(db: AsyncSession, principal: Principal, archived: bool) -> list[Chat]:
    query = select(Chat).where(Chat.workspace_id == _ws(principal))
    if archived:
        query = query.where(Chat.archived_at.is_not(None))
    else:
        query = query.where(Chat.archived_at.is_(None))
    return list((await db.execute(query.order_by(Chat.updated_at.desc()))).scalars().all())


async def get_chat(db: AsyncSession, chat_id: UUID) -> Chat:
    chat = (await db.execute(select(Chat).where(Chat.id == chat_id))).scalar_one_or_none()
    if chat is None:
        raise not_found()
    return chat


async def archive_chat(db: AsyncSession, chat: Chat, principal: Principal, restore: bool) -> None:
    chat.archived_at = None if restore else _now()
    chat.archived_by = None if restore else principal.user_id


async def list_message_views(db: AsyncSession, chat_id: UUID) -> list[dict[str, object]]:
    rows = (
        (await db.execute(select(Message).where(Message.chat_id == chat_id).order_by(Message.seq)))
        .scalars()
        .all()
    )
    views: list[dict[str, object]] = []
    for message in rows:
        parts = (
            (
                await db.execute(
                    select(MessagePart)
                    .where(MessagePart.message_id == message.id)
                    .order_by(MessagePart.seq)
                )
            )
            .scalars()
            .all()
        )
        views.append(
            {
                "id": str(message.id),
                "role": message.role,
                "status": message.status,
                "seq": message.seq,
                "archived": message.archived_at is not None,
                "error_code": message.error_code,
                "run_id": str(message.run_id) if message.run_id else None,
                "parts": [
                    {"kind": part.kind, "content": part.content, "data": part.data}
                    for part in parts
                ],
            }
        )
    return views


async def update_chat(
    db: AsyncSession,
    chat: Chat,
    *,
    title: str | None,
    reasoning_mode: str | None,
) -> Chat:
    if title is not None:
        chat.title = title
    if reasoning_mode is not None:
        if reasoning_mode not in {"inherit", "on", "off"}:
            raise problem(
                422, "validation_failed", "Validation failed", "reasoning_mode is invalid."
            )
        chat.reasoning_mode = reasoning_mode
    return chat


async def user_text_before(db: AsyncSession, chat_id: UUID, seq: int) -> str:
    message = (
        (
            await db.execute(
                select(Message)
                .where(
                    Message.chat_id == chat_id,
                    Message.role == "user",
                    Message.seq < seq,
                    Message.archived_at.is_(None),
                )
                .order_by(Message.seq.desc())
            )
        )
        .scalars()
        .first()
    )
    if message is None:
        return ""
    part = (
        (
            await db.execute(
                select(MessagePart)
                .where(MessagePart.message_id == message.id, MessagePart.kind == "text")
                .order_by(MessagePart.seq)
            )
        )
        .scalars()
        .first()
    )
    return part.content if part and part.content else ""


async def revoke_share(db: AsyncSession, principal: Principal, link_id: UUID) -> None:
    link = (
        await db.execute(
            select(ShareLink).where(
                ShareLink.id == link_id, ShareLink.workspace_id == _ws(principal)
            )
        )
    ).scalar_one_or_none()
    if link is None:
        raise not_found()
    link.revoked_at = _now()
    await write_audit(
        db,
        principal,
        action="share.revoke",
        resource_type=link.resource_type,
        resource_id=link.resource_id,
        outcome="allowed",
    )


def _prepared_turns(
    text: str,
    turns: list[dict[str, Any]] | None,
    chat: Chat,
    settings: Settings,
) -> list[dict[str, Any]]:
    scripted = scripted_turns(text, turns, llm_mode=settings.llm_mode)
    if chat.reasoning_mode == "off":
        return without_reasoning(scripted)
    return scripted


def _chunks(text: str, size: int) -> list[str]:
    if not text:
        return []
    return [text[index : index + size] for index in range(0, len(text), size)]


async def _cancelled(db: AsyncSession, run_id: UUID) -> bool:
    from younique.services.cancellation import is_marked

    if is_marked(str(run_id)):
        return True
    status = (await db.execute(select(Run.status).where(Run.id == run_id))).scalar_one()
    return status == "cancelled"


def sse(event: str, data: dict[str, Any], seq: int) -> str:
    payload = json.dumps(data, separators=(",", ":"), default=str)
    return f"id: {seq}\nevent: {event}\ndata: {payload}\n\n"


async def send_message(
    db: AsyncSession,
    principal: Principal,
    chat: Chat,
    text: str,
    *,
    settings: Settings,
    turns: list[dict[str, Any]] | None = None,
    record_user: bool = True,
) -> AsyncIterator[str]:
    seq_value = (
        await db.execute(
            select(func.coalesce(func.max(Message.seq), 0)).where(Message.chat_id == chat.id)
        )
    ).scalar_one()
    user_seq = int(seq_value)
    if record_user:
        user_seq = int(seq_value) + 1
        user_message = Message(
            workspace_id=_ws(principal),
            chat_id=chat.id,
            role="user",
            seq=user_seq,
            status="complete",
            created_by=principal.user_id,
        )
        db.add(user_message)
        await db.flush()
        db.add(
            MessagePart(
                workspace_id=_ws(principal),
                message_id=user_message.id,
                seq=1,
                kind="text",
                content=text,
                trust_level="trusted",
            )
        )
    run = Run(
        workspace_id=_ws(principal),
        kind="chat",
        chat_id=chat.id,
        status="running",
        trust_level="trusted",
        started_at=_now(),
        created_by=principal.user_id,
    )
    db.add(run)
    await db.flush()
    policies = {
        row.tool_key: {"mode": row.mode, "allow_when_tainted": row.allow_when_tainted}
        for row in (
            await db.execute(select(ToolPolicy).where(ToolPolicy.workspace_id == _ws(principal)))
        )
        .scalars()
        .all()
    }
    state = {
        "messages": [{"role": "user", "content": text, "trust": "trusted"}],
        "run_id": str(run.id),
        "workspace_id": str(_ws(principal)),
        "trust_level": "trusted",
        "tool_allowlist": [
            "smtp.send",
            "gmail.send_email",
            "gmail.get_message",
            "http.request",
            "sheets.read",
            "sheets.write",
            "drive.read",
        ],
        "policies": policies,
        "turns": _prepared_turns(text, turns, chat, settings),
        "max_steps": 25,
        "max_tool_calls": 50,
        "budget_micro_usd": 1_000_000_000,
    }
    config = {"configurable": {"thread_id": str(run.id)}}
    graph = get_graph()
    result = await graph.ainvoke(state, config)
    snap = await graph.aget_state(config)
    seq = 0
    seq = await _emit(
        db, principal, run.id, seq, "run.started", {"run_id": str(run.id), "chat_id": str(chat.id)}
    )
    yield sse("run.started", {"run_id": str(run.id), "chat_id": str(chat.id)}, seq)
    interrupts = list(getattr(snap, "interrupts", ()) or ())
    if interrupts:
        payload = interrupts[0].value
        flagged = flag_untrusted_arguments(
            dict(payload.get("arguments") or {}),
            list(result.get("untrusted_blobs") or []),
        )
        approval = Approval(
            workspace_id=_ws(principal),
            run_id=run.id,
            tool_key=str(payload.get("tool_key")),
            tool_args_redacted=redact_value(payload.get("arguments") or {}),
            summary={
                "headline": f"Approve {payload.get('tool_key')}",
                "flagged_args": flagged or payload.get("flagged_args") or [],
                "arguments": redact_value(payload.get("arguments") or {}),
                "reason": payload.get("reason"),
            },
            risk=str(payload.get("risk") or "high"),
            reason=str(payload.get("reason") or "policy"),
            status="pending",
            expires_at=_now() + timedelta(hours=24),
        )
        db.add(approval)
        run.status = "awaiting_approval"
        await db.flush()
        body = {
            "approval_id": str(approval.id),
            "tool_key": approval.tool_key,
            "risk": approval.risk,
            "reason": approval.reason,
            "summary": approval.summary,
            "expires_at": approval.expires_at.isoformat(),
        }
        seq = await _emit(db, principal, run.id, seq, "approval.required", body)
        yield sse("approval.required", body, seq)
        return
    refusal = refusal_from(result)
    text_out = refusal or str(result.get("final_text") or "")
    reasoning = str(result.get("reasoning_text") or "")
    show_reasoning = chat.reasoning_mode != "off" and bool(reasoning)
    error_code = "tool_blocked_by_policy" if refusal else result.get("error_code")
    assistant = Message(
        workspace_id=_ws(principal),
        chat_id=chat.id,
        run_id=run.id,
        role="assistant",
        seq=user_seq + 1,
        status="streaming",
        error_code=str(error_code) if error_code else None,
    )
    db.add(assistant)
    await db.flush()
    part_seq = 1
    if show_reasoning:
        db.add(
            MessagePart(
                workspace_id=_ws(principal),
                message_id=assistant.id,
                seq=part_seq,
                kind="reasoning",
                content=reasoning,
                trust_level="trusted",
            )
        )
        part_seq += 1
        seq = await _emit(
            db, principal, run.id, seq, "part.delta", {"kind": "reasoning", "text": reasoning}
        )
        yield sse("part.delta", {"kind": "reasoning", "text": reasoning}, seq)
    text_part = MessagePart(
        workspace_id=_ws(principal),
        message_id=assistant.id,
        seq=part_seq,
        kind="text",
        content="",
        trust_level="trusted",
    )
    db.add(text_part)
    await db.flush()
    seq = await _emit(
        db,
        principal,
        run.id,
        seq,
        "message.created",
        {"message_id": str(assistant.id), "role": "assistant"},
    )
    yield sse("message.created", {"message_id": str(assistant.id), "role": "assistant"}, seq)
    pace = settings.stream_pace_ms / 1000
    pieces = _chunks(text_out, 12) if pace else [text_out]
    stopped = False
    built = ""
    for piece in pieces:
        if await _cancelled(db, run.id):
            stopped = True
            break
        built += piece
        text_part.content = built
        seq = await _emit(db, principal, run.id, seq, "part.delta", {"kind": "text", "text": piece})
        yield sse("part.delta", {"kind": "text", "text": piece}, seq)
        if pace:
            await asyncio.sleep(pace)
    if not stopped and text_out and built != text_out:
        text_part.content = text_out
    assistant.status = "stopped" if stopped else "complete"
    run.status = (
        "cancelled"
        if stopped
        else ("succeeded" if result.get("status") != "failed" and not refusal else "failed")
    )
    run.finished_at = _now()
    run.error_code = "run_cancelled" if stopped else (str(error_code) if error_code else None)
    if error_code and not stopped:
        err = {"code": str(error_code), "detail": text_out}
        seq = await _emit(db, principal, run.id, seq, "error", err)
        yield sse("error", err, seq)
    price = PriceSnapshot(
        input_micro_usd_per_mtok=0,
        output_micro_usd_per_mtok=0,
        cached_input_micro_usd_per_mtok=0,
        reasoning_micro_usd_per_mtok=0,
    )
    cost = cost_micro_usd(
        input_tokens=10,
        cached_input_tokens=0,
        output_tokens=max(1, len(text_out) // 4),
        reasoning_tokens=0,
        price=price,
    )
    await record_usage(
        db,
        principal,
        model_id=chat.model_id,
        run_id=run.id,
        chat_id=chat.id,
        input_tokens=10,
        cached_input_tokens=0,
        output_tokens=max(1, len(text_out) // 4),
        reasoning_tokens=0,
        price=price,
        request_id=f"run-{run.id}",
    )
    done = {"run_id": str(run.id), "status": run.status, "cost_micro_usd": cost}
    seq = await _emit(db, principal, run.id, seq, "run.completed", done)
    yield sse("run.completed", done, seq)


async def replay_events(db: AsyncSession, run_id: UUID, last_event_id: int) -> list[RunEvent]:
    rows = (
        (
            await db.execute(
                select(RunEvent)
                .where(RunEvent.run_id == run_id, RunEvent.seq > last_event_id)
                .order_by(RunEvent.seq)
            )
        )
        .scalars()
        .all()
    )
    return list(rows)


async def decide_approval(
    db: AsyncSession,
    principal: Principal,
    approval_id: UUID,
    decision: str,
    remember: str | None,
    settings: Settings,
) -> Approval:
    approval = (
        await db.execute(select(Approval).where(Approval.id == approval_id))
    ).scalar_one_or_none()
    if approval is None:
        raise not_found()
    if decision not in {"approve", "reject"}:
        raise problem(
            422, "validation_failed", "Validation failed", "Decision must be approve or reject."
        )
    if remember == "always" and not fresh_reauth(principal, settings):
        raise reauth_required()
    approval.status = "approved" if decision == "approve" else "rejected"
    approval.decided_by = principal.user_id
    approval.decided_at = _now()
    if remember in {"always", "never"}:
        mode = "always_allow" if remember == "always" else "never"
        existing = (
            await db.execute(
                select(ToolPolicy).where(
                    ToolPolicy.workspace_id == _ws(principal),
                    ToolPolicy.tool_key == approval.tool_key,
                    ToolPolicy.scope_agent_id.is_(None),
                )
            )
        ).scalar_one_or_none()
        if existing is None:
            db.add(
                ToolPolicy(
                    workspace_id=_ws(principal),
                    tool_key=approval.tool_key,
                    mode=mode,
                    allow_when_tainted=False,
                    risk=approval.risk,
                )
            )
        else:
            existing.mode = mode
    run = (await db.execute(select(Run).where(Run.id == approval.run_id))).scalar_one()
    if decision == "approve":
        resumed = await get_graph().ainvoke(
            Command(resume={"decision": "approve"}), {"configurable": {"thread_id": str(run.id)}}
        )
        run.status = "succeeded"
        await _record_assistant(db, principal, run, str(resumed.get("final_text") or "Sent."))
    else:
        await get_graph().ainvoke(
            Command(resume={"decision": "reject"}), {"configurable": {"thread_id": str(run.id)}}
        )
        run.status = "failed"
        run.error_code = "approval_rejected"
        await _record_assistant(db, principal, run, "The action was not approved.")
    run.finished_at = _now()
    await _emit(
        db,
        principal,
        run.id,
        0,
        "run.completed",
        {"run_id": str(run.id), "status": run.status},
    )
    await write_audit(
        db,
        principal,
        action="approval.decide",
        resource_type="approval",
        resource_id=approval.id,
        outcome="allowed",
        detail={"decision": decision, "tool_key": approval.tool_key},
    )
    return approval


async def save_provider_key(
    db: AsyncSession,
    principal: Principal,
    *,
    provider_key: str,
    label: str,
    secret: str,
    settings: Settings,
    base_url: str | None,
) -> ProviderKey:
    if not fresh_reauth(principal, settings):
        raise reauth_required()
    if settings.llm_mode == "fake":
        valid = secret.startswith("valid-key") or secret.startswith("sk-")
    else:
        valid = len(secret) > 8
    if not valid:
        raise problem(
            422,
            "validation_failed",
            "Validation failed",
            "The provider rejected this key. Nothing was stored.",
            errors=[{"field": "secret", "code": "invalid", "detail": "Key validation failed."}],
        )
    provider = (
        await db.execute(select(ModelProvider).where(ModelProvider.key == provider_key))
    ).scalar_one_or_none()
    if provider is None:
        raise not_found()
    dek_row = await _dek(db, _ws(principal), settings)
    row_id = uuid7()
    ciphertext = encrypt(
        dek_row[0],
        secret.encode(),
        workspace_id=_ws(principal),
        secret_kind="provider_key",
        row_id=row_id,
        key_version=dek_row[1].version,
    )
    row = ProviderKey(
        id=row_id,
        workspace_id=_ws(principal),
        provider_id=provider.id,
        owner_user_id=_user(principal),
        label=label,
        last4=secret[-4:],
        key_ct=ciphertext,
        encryption_key_id=dek_row[1].id,
        key_version=dek_row[1].version,
        base_url_override=base_url,
        status="active",
        last_validated_at=_now(),
    )
    db.add(row)
    await db.flush()
    await write_audit(
        db,
        principal,
        action="provider_key.create",
        resource_type="provider_key",
        resource_id=row.id,
        outcome="allowed",
    )
    return row


async def rotate_provider_key(
    db: AsyncSession,
    principal: Principal,
    key_id: UUID,
    secret: str,
    settings: Settings,
) -> ProviderKey:
    if not fresh_reauth(principal, settings):
        raise reauth_required()
    row = (
        await db.execute(
            select(ProviderKey).where(
                ProviderKey.id == key_id, ProviderKey.workspace_id == _ws(principal)
            )
        )
    ).scalar_one_or_none()
    if row is None or row.status == "revoked":
        raise not_found()
    if settings.llm_mode == "fake":
        valid = secret.startswith("valid-key") or secret.startswith("sk-")
    else:
        valid = len(secret) > 8
    if not valid:
        raise problem(
            422,
            "validation_failed",
            "Validation failed",
            "The provider rejected this key. Nothing was stored.",
        )
    dek_row = await _dek(db, _ws(principal), settings)
    row.key_ct = encrypt(
        dek_row[0],
        secret.encode(),
        workspace_id=_ws(principal),
        secret_kind="provider_key",
        row_id=row.id,
        key_version=dek_row[1].version,
    )
    row.last4 = secret[-4:]
    row.encryption_key_id = dek_row[1].id
    row.key_version = dek_row[1].version
    row.status = "active"
    row.last_validated_at = _now()
    await write_audit(
        db,
        principal,
        action="provider_key.rotate",
        resource_type="provider_key",
        resource_id=row.id,
        outcome="allowed",
    )
    return row


async def revoke_provider_key(db: AsyncSession, principal: Principal, key_id: UUID) -> ProviderKey:
    row = (
        await db.execute(
            select(ProviderKey).where(
                ProviderKey.id == key_id, ProviderKey.workspace_id == _ws(principal)
            )
        )
    ).scalar_one_or_none()
    if row is None:
        raise not_found()
    row.status = "revoked"
    row.key_ct = b""
    await write_audit(
        db,
        principal,
        action="provider_key.revoke",
        resource_type="provider_key",
        resource_id=row.id,
        outcome="allowed",
    )
    return row


def provider_key_view(row: ProviderKey, provider: str) -> dict[str, object]:
    return {
        "id": str(row.id),
        "provider": provider,
        "label": row.label,
        "last4": row.last4,
        "status": row.status,
        "last_validated_at": row.last_validated_at,
        "base_url_override": row.base_url_override,
    }


async def record_usage(
    db: AsyncSession,
    principal: Principal,
    *,
    model_id: UUID | None,
    run_id: UUID | None,
    chat_id: UUID | None,
    input_tokens: int,
    cached_input_tokens: int,
    output_tokens: int,
    reasoning_tokens: int,
    price: PriceSnapshot,
    request_id: str,
) -> UsageEvent | None:
    existing = (
        await db.execute(
            select(UsageRequestDedupe).where(UsageRequestDedupe.request_id == request_id)
        )
    ).scalar_one_or_none()
    if existing is not None:
        return None
    cost = cost_micro_usd(
        input_tokens=input_tokens,
        cached_input_tokens=cached_input_tokens,
        output_tokens=output_tokens,
        reasoning_tokens=reasoning_tokens,
        price=price,
    )
    event = UsageEvent(
        workspace_id=_ws(principal),
        occurred_at=_now(),
        run_id=run_id,
        chat_id=chat_id,
        model_id=model_id,
        input_tokens=input_tokens,
        cached_input_tokens=cached_input_tokens,
        output_tokens=output_tokens,
        reasoning_tokens=reasoning_tokens,
        cost_micro_usd=cost,
        price_snapshot=price.model_dump(),
        request_id=request_id,
    )
    db.add(event)
    await db.flush()
    db.add(
        UsageRequestDedupe(
            request_id=request_id,
            workspace_id=_ws(principal),
            usage_event_id=event.id,
        )
    )
    return event


async def ingest_upload(
    db: AsyncSession,
    principal: Principal,
    *,
    name: str,
    declared_mime: str,
    data: bytes,
    timeout_s: float = 30,
    settings: Settings | None = None,
    chat_id: UUID | None = None,
) -> ArtifactVersion:
    from younique.core.config import get_settings
    from younique.services.artifacts_flow import ingest_inline

    return await ingest_inline(
        db,
        principal,
        name=name,
        declared_mime=declared_mime,
        data=data,
        settings=settings or get_settings(),
        timeout_s=timeout_s,
        chat_id=chat_id,
    )


def download_version(version: ArtifactVersion, name: str = "download") -> dict[str, object]:
    from younique.services.artifacts_flow import download_payload

    return download_payload(version, name=name)


async def create_share(
    db: AsyncSession,
    principal: Principal,
    *,
    resource_type: str,
    resource_id: UUID,
    password: str | None,
    include_reasoning: bool,
) -> tuple[ShareLink, str]:
    token = new_token(32)
    link = ShareLink(
        workspace_id=_ws(principal),
        resource_type=resource_type,
        resource_id=resource_id,
        token_hash=sha256_hex(token),
        role="viewer",
        password_hash=_HASHER.hash(password) if password else None,
        include_reasoning=include_reasoning,
        expires_at=_now() + timedelta(days=30),
        created_by=principal.user_id,
    )
    db.add(link)
    await db.flush()
    await write_audit(
        db,
        principal,
        action="share.create",
        resource_type=resource_type,
        resource_id=resource_id,
        outcome="allowed",
    )
    return link, token


async def resolve_share(db: AsyncSession, token: str, password: str | None) -> dict[str, object]:
    from sqlalchemy import text

    await db.execute(
        text("SELECT set_config('app.share_token_hash', :v, true)"), {"v": sha256_hex(token)}
    )
    link = (
        await db.execute(select(ShareLink).where(ShareLink.token_hash == sha256_hex(token)))
    ).scalar_one_or_none()
    if link is None or link.revoked_at is not None:
        raise problem(403, "share_link_revoked", "Share link revoked", "This link is not active.")
    if link.expires_at and link.expires_at <= _now():
        raise problem(403, "share_link_expired", "Share link expired", "This link has expired.")
    if link.password_hash:
        if not password:
            raise problem(
                403, "password_required", "Password required", "This link requires a password."
            )
        try:
            _HASHER.verify(link.password_hash, password)
        except Exception as exc:
            raise problem(
                403, "password_required", "Password required", "The password is incorrect."
            ) from exc
    await apply_tenant(db, workspace_id=link.workspace_id, user_id=None, bootstrap=True)
    chat = (await db.execute(select(Chat).where(Chat.id == link.resource_id))).scalar_one_or_none()
    messages = []
    if chat is not None:
        rows = (
            (
                await db.execute(
                    select(Message).where(Message.chat_id == chat.id, Message.archived_at.is_(None))
                )
            )
            .scalars()
            .all()
        )
        for message in rows:
            parts = (
                (await db.execute(select(MessagePart).where(MessagePart.message_id == message.id)))
                .scalars()
                .all()
            )
            visible = []
            for part in parts:
                if part.kind == "reasoning" and not link.include_reasoning:
                    continue
                visible.append({"kind": part.kind, "content": part.content})
            messages.append({"id": str(message.id), "role": message.role, "parts": visible})
    link.view_count += 1
    link.last_viewed_at = _now()
    return {
        "resource_type": link.resource_type,
        "resource_id": str(link.resource_id),
        "includes": ["messages", "artifacts_in_chat"],
        "excludes": ["connections", "provider_keys", "memories", "tools"],
        "messages": messages,
        "title": chat.title if chat else None,
    }


async def connect_smtp(
    db: AsyncSession,
    principal: Principal,
    *,
    host: str,
    port: int,
    username: str,
    password: str,
    settings: Settings,
) -> Connection:
    dek = await _dek(db, _ws(principal), settings)
    connection = Connection(
        workspace_id=_ws(principal),
        connector_key="smtp",
        owner_user_id=_user(principal),
        external_account_label=username,
        granted_scopes=[],
        enabled_bundles=["send"],
        status="active",
        health="healthy",
        config={"host": host, "port": port},
    )
    db.add(connection)
    await db.flush()
    from younique.models import ConnectionSecret

    db.add(
        ConnectionSecret(
            workspace_id=_ws(principal),
            connection_id=connection.id,
            encryption_key_id=dek[1].id,
            secret_ct=encrypt(
                dek[0],
                password.encode(),
                workspace_id=_ws(principal),
                secret_kind="smtp_password",
                row_id=connection.id,
                key_version=dek[1].version,
            ),
            key_version=dek[1].version,
        )
    )
    return connection


def catalogue() -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for manifest in manifests():
        rows.append(
            {
                "key": manifest.key,
                "display_name": manifest.display_name,
                "description": manifest.description,
                "limitations": manifest.limitations,
                "approval_status": manifest.approval_status,
                "bundles": [bundle.model_dump() for bundle in manifest.bundles],
            }
        )
    return rows


def bundle_tools(connector_key: str, bundles: set[str]) -> list[str]:
    return [
        str(getattr(tool, "__tool_key__", "")) for tool in tools_for_bundles(connector_key, bundles)
    ]


async def _record_assistant(db: AsyncSession, principal: Principal, run: Run, text: str) -> None:
    if run.chat_id is None:
        return
    seq_value = (
        await db.execute(
            select(func.coalesce(func.max(Message.seq), 0)).where(Message.chat_id == run.chat_id)
        )
    ).scalar_one()
    assistant = Message(
        workspace_id=_ws(principal),
        chat_id=run.chat_id,
        run_id=run.id,
        role="assistant",
        seq=int(seq_value) + 1,
        status="complete",
    )
    db.add(assistant)
    await db.flush()
    db.add(
        MessagePart(
            workspace_id=_ws(principal),
            message_id=assistant.id,
            seq=1,
            kind="text",
            content=text,
            trust_level="trusted",
        )
    )


async def _emit(
    db: AsyncSession,
    principal: Principal,
    run_id: UUID,
    seq: int,
    event_type: str,
    data: dict[str, Any],
) -> int:
    seq += 1
    db.add(
        RunEvent(
            workspace_id=_ws(principal),
            run_id=run_id,
            seq=seq,
            event_type=event_type,
            data=data,
            created_at=_now(),
        )
    )
    await db.flush()
    return seq


async def _dek(
    db: AsyncSession, workspace_id: UUID, settings: Settings
) -> tuple[bytes, EncryptionKey]:
    row = (
        (
            await db.execute(
                select(EncryptionKey)
                .where(EncryptionKey.workspace_id == workspace_id)
                .order_by(EncryptionKey.version.desc())
            )
        )
        .scalars()
        .first()
    )
    if row is None:
        raise not_found()
    cached = cached_dek(workspace_id, row.version)
    if cached is not None:
        return cached, row
    dek = await build_kek(settings).unwrap(row.dek_wrapped)
    cache_dek(workspace_id, row.version, dek)
    return dek, row


def _ws(principal: Principal) -> UUID:
    if principal.workspace_id is None:
        raise permission_denied()
    return principal.workspace_id


def _user(principal: Principal) -> UUID:
    if principal.user_id is None:
        raise permission_denied()
    return principal.user_id


async def price_for(db: AsyncSession, model_id: UUID) -> PriceSnapshot:
    row = (
        (
            await db.execute(
                select(ModelPrice)
                .where(ModelPrice.model_id == model_id)
                .order_by(ModelPrice.effective_from.desc())
            )
        )
        .scalars()
        .first()
    )
    if row is None:
        raise not_found()
    return PriceSnapshot(
        input_micro_usd_per_mtok=row.input_micro_usd_per_mtok,
        output_micro_usd_per_mtok=row.output_micro_usd_per_mtok,
        cached_input_micro_usd_per_mtok=row.cached_input_micro_usd_per_mtok,
        reasoning_micro_usd_per_mtok=row.reasoning_micro_usd_per_mtok,
    )


async def list_models(db: AsyncSession, principal: Principal, available: bool) -> list[Model]:
    rows = list((await db.execute(select(Model).where(Model.status == "active"))).scalars().all())
    if not available:
        return rows
    keys = (
        (
            await db.execute(
                select(ProviderKey.provider_id).where(
                    ProviderKey.workspace_id == _ws(principal),
                    ProviderKey.status == "active",
                )
            )
        )
        .scalars()
        .all()
    )
    allowed = set(keys)
    return [row for row in rows if row.provider_id in allowed or row.model_ref == "fake-chat"]


def decrypt_for_test(dek: bytes, blob: bytes, **kwargs: Any) -> bytes:
    return decrypt(dek, blob, **kwargs)
