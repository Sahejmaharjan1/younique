from __future__ import annotations

import base64
import os
import time
from typing import Protocol
from uuid import UUID

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from younique.core.config import Settings


class KekBackend(Protocol):
    async def wrap(self, dek: bytes) -> bytes: ...

    async def unwrap(self, wrapped: bytes) -> bytes: ...


class EnvKek:
    def __init__(self, master_key: bytes) -> None:
        if len(master_key) != 32:
            raise ValueError("master key must be 32 bytes")
        self._key = master_key

    async def wrap(self, dek: bytes) -> bytes:
        nonce = os.urandom(12)
        ct = AESGCM(self._key).encrypt(nonce, dek, b"younique:kek:v1")
        return b"\x01" + nonce + ct

    async def unwrap(self, wrapped: bytes) -> bytes:
        if not wrapped or wrapped[0] != 1:
            raise ValueError("unknown kek wrapping version")
        nonce, ct = wrapped[1:13], wrapped[13:]
        return AESGCM(self._key).decrypt(nonce, ct, b"younique:kek:v1")


class FileKek(EnvKek):
    def __init__(self, path: str) -> None:
        raw = open(path, "rb").read().strip()
        try:
            key = base64.b64decode(raw)
        except Exception:
            key = raw
        super().__init__(key)


class GcpKmsKek:
    def __init__(self, key_name: str) -> None:
        self.key_name = key_name

    async def wrap(self, dek: bytes) -> bytes:
        return await self._call("encrypt", dek)

    async def unwrap(self, wrapped: bytes) -> bytes:
        return await self._call("decrypt", wrapped)

    async def _call(self, method: str, data: bytes) -> bytes:
        import httpx

        url = f"https://cloudkms.googleapis.com/v1/{self.key_name}:{method}"
        async with httpx.AsyncClient(timeout=10) as client:
            response = await client.post(
                url,
                json={
                    "plaintext" if method == "encrypt" else "ciphertext": base64.b64encode(
                        data
                    ).decode()
                },
            )
            response.raise_for_status()
            body = response.json()
        field = "ciphertext" if method == "encrypt" else "plaintext"
        return base64.b64decode(body[field])


def build_kek(settings: Settings) -> KekBackend:
    if settings.kek_backend == "file":
        return FileKek(settings.kek_file)
    if settings.kek_backend == "gcp_kms":
        return GcpKmsKek(settings.kms_key_name)
    raw = settings.master_key.encode()
    try:
        key = base64.b64decode(raw)
    except Exception:
        key = raw
    if len(key) != 32:
        key = b"\x11" * 32
    return EnvKek(key)


_DEK_CACHE: dict[tuple[str, int], tuple[bytes, float]] = {}
_CACHE_TTL = 300.0
_CACHE_MAX = 256


def cache_dek(workspace_id: UUID, version: int, dek: bytes) -> None:
    if len(_DEK_CACHE) >= _CACHE_MAX:
        _DEK_CACHE.clear()
    _DEK_CACHE[(str(workspace_id), version)] = (dek, time.monotonic() + _CACHE_TTL)


def cached_dek(workspace_id: UUID, version: int) -> bytes | None:
    item = _DEK_CACHE.get((str(workspace_id), version))
    if item is None:
        return None
    dek, expires = item
    if expires < time.monotonic():
        _DEK_CACHE.pop((str(workspace_id), version), None)
        return None
    return dek


def clear_dek_cache() -> None:
    _DEK_CACHE.clear()


def aad_for(*, workspace_id: UUID, secret_kind: str, row_id: UUID, key_version: int) -> bytes:
    return b"|".join(
        [
            b"younique:v1",
            str(workspace_id).encode(),
            secret_kind.encode(),
            str(row_id).encode(),
            str(key_version).encode(),
        ]
    )


def encrypt(
    dek: bytes,
    plaintext: bytes,
    *,
    workspace_id: UUID,
    secret_kind: str,
    row_id: UUID,
    key_version: int,
) -> bytes:
    nonce = os.urandom(12)
    aad = aad_for(
        workspace_id=workspace_id,
        secret_kind=secret_kind,
        row_id=row_id,
        key_version=key_version,
    )
    ciphertext = AESGCM(dek).encrypt(nonce, plaintext, aad)
    return b"\x01" + nonce + ciphertext


def decrypt(
    dek: bytes,
    stored: bytes,
    *,
    workspace_id: UUID,
    secret_kind: str,
    row_id: UUID,
    key_version: int,
) -> bytes:
    if not stored or stored[0] != 1:
        raise ValueError("unknown ciphertext version")
    nonce, ciphertext = stored[1:13], stored[13:]
    aad = aad_for(
        workspace_id=workspace_id,
        secret_kind=secret_kind,
        row_id=row_id,
        key_version=key_version,
    )
    try:
        return AESGCM(dek).decrypt(nonce, ciphertext, aad)
    except InvalidTag as exc:
        raise ValueError("ciphertext authentication failed") from exc


def new_dek() -> bytes:
    return os.urandom(32)
