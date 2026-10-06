from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Literal, cast
from uuid import UUID

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession
from uuid6 import uuid7

from younique.agents.graph import TOOL_RISK
from younique.authz.principal import Principal
from younique.core.config import Settings
from younique.core.db import apply_tenant
from younique.core.errors import session_expired, session_revoked, unauthenticated
from younique.core.security import new_token, sha256_hex
from younique.crypto.envelope import build_kek, cache_dek, new_dek
from younique.models import (
    ConsentAcceptance,
    ConsentDocument,
    Device,
    EncryptionKey,
    Identity,
    MemorySet,
    Session,
    ToolPolicy,
    User,
    Workspace,
    WorkspaceMember,
)

HIGH_RISK_TOOLS = (
    "smtp.send",
    "gmail.send_email",
    "http.request",
    "sheets.write",
)


@dataclass
class IssuedSession:
    token: str
    csrf: str
    user: User
    workspace: Workspace
    principal: Principal
    consent_required: list[dict[str, object]]


def _now() -> datetime:
    return datetime.now(UTC)


async def exchange_session(
    db: AsyncSession,
    *,
    claims: dict[str, object],
    settings: Settings,
    user_agent: str,
    ip: str | None,
    existing_token: str | None,
    step_up: bool,
) -> IssuedSession:
    firebase_uid = str(claims.get("sub") or claims.get("user_id") or "")
    email = str(claims.get("email") or f"{firebase_uid}@users.younique.local")
    provider = "password"
    firebase = claims.get("firebase")
    if isinstance(firebase, dict):
        sign_in = str(firebase.get("sign_in_provider") or "password")
        provider = {"google.com": "google", "github.com": "github", "password": "password"}.get(
            sign_in, "password"
        )
    await apply_tenant(db, workspace_id=None, user_id=None, bootstrap=False)
    await db.execute(text("SELECT set_config('app.firebase_uid', :v, true)"), {"v": firebase_uid})
    identity = (
        await db.execute(select(Identity).where(Identity.firebase_uid == firebase_uid))
    ).scalar_one_or_none()
    group_id: UUID | None = None
    csrf = new_token(16)
    if existing_token:
        prior = await _session_by_token(db, existing_token)
        if prior and prior.revoked_at is None and prior.expires_at > _now():
            group_id = prior.session_group_id
            csrf_row = prior.csrf_hash
            if csrf_row:
                csrf = existing_token
    if identity is None:
        issued = await _bootstrap(
            db,
            settings=settings,
            firebase_uid=firebase_uid,
            email=email,
            provider=provider,
            name=str(claims.get("name") or email.split("@")[0]),
            user_agent=user_agent,
            ip=ip,
            group_id=group_id or uuid7(),
            csrf=csrf,
        )
        return issued
    await apply_tenant(db, workspace_id=None, user_id=identity.user_id, bootstrap=False)
    user = (await db.execute(select(User).where(User.id == identity.user_id))).scalar_one()
    if step_up and existing_token:
        current = await _session_by_token(db, existing_token)
        if current and current.user_id == user.id and current.revoked_at is None:
            current.reauthed_at = _now()
            await db.flush()
            workspace = await _workspace_for(db, user)
            principal = await _principal(db, user, workspace, current)
            return IssuedSession(
                token=existing_token,
                csrf=csrf,
                user=user,
                workspace=workspace,
                principal=principal,
                consent_required=await missing_consents(db, user.id),
            )
    workspace = await _workspace_for(db, user)
    device = Device(
        user_id=user.id,
        fingerprint_hash=sha256_hex(user_agent or "unknown"),
        user_agent=user_agent,
        last_ip=ip,
        last_seen_at=_now(),
    )
    db.add(device)
    await db.flush()
    token = new_token(32)
    session = Session(
        user_id=user.id,
        device_id=device.id,
        token_hash=sha256_hex(token),
        session_group_id=group_id or uuid7(),
        active_workspace_id=workspace.id,
        csrf_hash=sha256_hex(csrf),
        expires_at=_now() + timedelta(days=settings.session_idle_days),
        absolute_expires_at=_now() + timedelta(days=settings.session_absolute_days),
        reauthed_at=_now() if step_up else None,
        last_seen_at=_now(),
    )
    await apply_tenant(db, workspace_id=workspace.id, user_id=user.id, bootstrap=True)
    db.add(session)
    await db.flush()
    principal = await _principal(db, user, workspace, session)
    return IssuedSession(
        token=token,
        csrf=csrf,
        user=user,
        workspace=workspace,
        principal=principal,
        consent_required=await missing_consents(db, user.id),
    )


async def _bootstrap(
    db: AsyncSession,
    *,
    settings: Settings,
    firebase_uid: str,
    email: str,
    provider: str,
    name: str,
    user_agent: str,
    ip: str | None,
    group_id: UUID,
    csrf: str,
) -> IssuedSession:
    user_id = uuid7()
    workspace_id = uuid7()
    await apply_tenant(db, workspace_id=workspace_id, user_id=user_id, bootstrap=True)
    user = User(
        id=user_id,
        primary_email=email,
        display_name=name,
        timezone="UTC",
        preferences={"reasoning_default": "off", "memory_write_mode": "append"},
    )
    workspace = Workspace(id=workspace_id, slug=f"ws-{workspace_id.hex[:10]}", name=f"{name}'s workspace")
    db.add(user)
    db.add(workspace)
    await db.flush()
    user.default_workspace_id = workspace.id
    db.add(WorkspaceMember(workspace_id=workspace.id, user_id=user.id, role="owner"))
    db.add(
        Identity(
            user_id=user.id,
            provider=provider,
            firebase_uid=firebase_uid,
            provider_subject=firebase_uid,
            is_primary=True,
            email=email,
        )
    )
    db.add(
        MemorySet(
            workspace_id=workspace.id,
            scope="personal",
            owner_user_id=user.id,
            name="Personal",
            write_mode="append",
        )
    )
    dek = new_dek()
    kek = build_kek(settings)
    wrapped = await kek.wrap(dek)
    key_row = EncryptionKey(
        workspace_id=workspace.id,
        version=1,
        dek_wrapped=wrapped,
        kms_key_name=settings.kms_key_name or "env",
    )
    db.add(key_row)
    cache_dek(workspace.id, 1, dek)
    for tool_key in HIGH_RISK_TOOLS:
        db.add(
            ToolPolicy(
                workspace_id=workspace.id,
                tool_key=tool_key,
                mode="ask_each_time",
                allow_when_tainted=False,
                risk=TOOL_RISK.get(tool_key, "high"),
            )
        )
    device = Device(
        user_id=user.id,
        fingerprint_hash=sha256_hex(user_agent or "unknown"),
        user_agent=user_agent,
        last_ip=ip,
        last_seen_at=_now(),
    )
    db.add(device)
    await db.flush()
    token = new_token(32)
    session = Session(
        user_id=user.id,
        device_id=device.id,
        token_hash=sha256_hex(token),
        session_group_id=group_id,
        active_workspace_id=workspace.id,
        csrf_hash=sha256_hex(csrf),
        expires_at=_now() + timedelta(days=settings.session_idle_days),
        absolute_expires_at=_now() + timedelta(days=settings.session_absolute_days),
        reauthed_at=_now(),
        last_seen_at=_now(),
    )
    db.add(session)
    await db.flush()
    principal = Principal(
        kind="user",
        user_id=user.id,
        workspace_id=workspace.id,
        workspace_role="owner",
        session_id=session.id,
        reauthed_at=session.reauthed_at,
    )
    return IssuedSession(
        token=token,
        csrf=csrf,
        user=user,
        workspace=workspace,
        principal=principal,
        consent_required=await missing_consents(db, user.id),
    )


async def _workspace_for(db: AsyncSession, user: User) -> Workspace:
    members = (
        await db.execute(
            select(WorkspaceMember).where(
                WorkspaceMember.user_id == user.id,
                WorkspaceMember.archived_at.is_(None),
            )
        )
    ).scalars().all()
    if not members:
        raise unauthenticated("The account has no workspace.")
    preferred = user.default_workspace_id or members[0].workspace_id
    await apply_tenant(db, workspace_id=preferred, user_id=user.id, bootstrap=False)
    workspace = (await db.execute(select(Workspace).where(Workspace.id == preferred))).scalar_one()
    return workspace


async def _principal(db: AsyncSession, user: User, workspace: Workspace, session: Session) -> Principal:
    member = (
        await db.execute(
            select(WorkspaceMember).where(
                WorkspaceMember.user_id == user.id,
                WorkspaceMember.workspace_id == workspace.id,
                WorkspaceMember.archived_at.is_(None),
            )
        )
    ).scalar_one()
    return Principal(
        kind="user",
        user_id=user.id,
        workspace_id=workspace.id,
        workspace_role=_role(member.role),
        session_id=session.id,
        reauthed_at=session.reauthed_at,
    )


async def _session_by_token(db: AsyncSession, token: str) -> Session | None:
    await db.execute(
        text("SELECT set_config('app.session_token_hash', :v, true)"),
        {"v": sha256_hex(token)},
    )
    return (
        await db.execute(select(Session).where(Session.token_hash == sha256_hex(token)))
    ).scalar_one_or_none()


async def resolve_principal(
    db: AsyncSession,
    *,
    token: str | None,
    account_id: str | None,
    workspace_header: str | None,
    settings: Settings,
) -> Principal:
    if not token:
        raise unauthenticated()
    session = await _session_by_token(db, token)
    if session is None:
        raise unauthenticated()
    now = _now()
    if session.revoked_at is not None:
        raise session_revoked()
    if session.absolute_expires_at <= now or session.expires_at <= now:
        raise session_expired()
    await db.execute(
        text("SELECT set_config('app.session_group_id', :v, true)"),
        {"v": str(session.session_group_id)},
    )
    active = session
    if account_id and account_id != str(session.user_id):
        try:
            requested = UUID(account_id)
        except ValueError as exc:
            raise unauthenticated("The account id is invalid.") from exc
        other = (
            await db.execute(
                select(Session).where(
                    Session.user_id == requested,
                    Session.session_group_id == session.session_group_id,
                    Session.revoked_at.is_(None),
                    Session.expires_at > now,
                )
            )
        ).scalar_one_or_none()
        if other is None:
            raise session_expired(f"Account {account_id} is not signed in on this device.")
        active = other
    await apply_tenant(db, workspace_id=None, user_id=active.user_id, bootstrap=False)
    user = (await db.execute(select(User).where(User.id == active.user_id))).scalar_one()
    workspace_id = active.active_workspace_id or user.default_workspace_id
    if workspace_header:
        workspace_id = UUID(workspace_header)
    if workspace_id is None:
        raise unauthenticated("No active workspace.")
    await apply_tenant(db, workspace_id=workspace_id, user_id=user.id, bootstrap=False)
    member = (
        await db.execute(
            select(WorkspaceMember).where(
                WorkspaceMember.workspace_id == workspace_id,
                WorkspaceMember.user_id == user.id,
                WorkspaceMember.archived_at.is_(None),
            )
        )
    ).scalar_one_or_none()
    if member is None:
        raise unauthenticated("You are not a member of that workspace.")
    if active.last_seen_at <= now - timedelta(hours=1):
        active.last_seen_at = now
        proposed = now + timedelta(days=settings.session_idle_days)
        active.expires_at = min(proposed, active.absolute_expires_at)
    return Principal(
        kind="user",
        user_id=user.id,
        workspace_id=workspace_id,
        workspace_role=_role(member.role),
        session_id=active.id,
        reauthed_at=active.reauthed_at,
    )


def _role(value: str) -> Literal["owner", "admin", "member", "guest"]:
    if value in {"owner", "admin", "member", "guest"}:
        return cast(Literal["owner", "admin", "member", "guest"], value)
    return "guest"


async def missing_consents(db: AsyncSession, user_id: UUID) -> list[dict[str, object]]:
    docs = (
        await db.execute(
            select(ConsentDocument).where(
                ConsentDocument.is_required.is_(True),
                ConsentDocument.effective_at <= _now(),
            )
        )
    ).scalars().all()
    accepted = set(
        (
            await db.execute(
                select(ConsentAcceptance.consent_document_id).where(ConsentAcceptance.user_id == user_id)
            )
        ).scalars().all()
    )
    required: list[dict[str, object]] = []
    for doc in docs:
        if doc.id not in accepted:
            required.append(
                {
                    "kind": doc.kind,
                    "version": doc.version,
                    "url": doc.url,
                    "summary_of_changes": doc.summary_of_changes,
                    "id": str(doc.id),
                }
            )
    return required


def fresh_reauth(principal: Principal, settings: Settings) -> bool:
    if principal.reauthed_at is None:
        return False
    return principal.reauthed_at >= _now() - timedelta(seconds=settings.step_up_seconds)
