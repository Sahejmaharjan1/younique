from __future__ import annotations

import base64
import json
import time
from typing import Any

import httpx
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import padding
from cryptography.x509 import load_pem_x509_certificate

from younique.core.config import Settings
from younique.core.errors import unauthenticated

_certs: dict[str, Any] = {}
_certs_at: float = 0.0


def _b64url(segment: str) -> bytes:
    pad = "=" * (-len(segment) % 4)
    return base64.urlsafe_b64decode(segment + pad)


def _payload(token: str) -> dict[str, Any]:
    parts = token.split(".")
    if len(parts) != 3:
        raise unauthenticated("The identity token is malformed.")
    data = json.loads(_b64url(parts[1]))
    if not isinstance(data, dict):
        raise unauthenticated("The identity token is malformed.")
    return data


async def verify_id_token(token: str, settings: Settings) -> dict[str, Any]:
    if settings.firebase_auth_emulator_host:
        claims = _payload(token)
        exp = claims.get("exp")
        if isinstance(exp, int) and exp < int(time.time()):
            raise unauthenticated("The identity token is expired.")
        if "sub" not in claims and "user_id" not in claims:
            raise unauthenticated("The identity token has no subject.")
        claims.setdefault("sub", claims.get("user_id"))
        return claims
    header = json.loads(_b64url(token.split(".")[0]))
    kid = header.get("kid")
    if not isinstance(kid, str):
        raise unauthenticated("The identity token has no key id.")
    certs = await _google_certs()
    pem = certs.get(kid)
    if not isinstance(pem, str):
        raise unauthenticated("The identity token key is unknown.")
    cert = load_pem_x509_certificate(pem.encode())
    signing_input, signature = token.rsplit(".", 1)
    public_key: Any = cert.public_key()
    try:
        public_key.verify(
            _b64url(signature),
            signing_input.encode(),
            padding.PKCS1v15(),
            hashes.SHA256(),
        )
    except Exception as exc:
        raise unauthenticated("The identity token signature is invalid.") from exc
    claims = _payload(token)
    aud = claims.get("aud")
    if aud != settings.firebase_project_id:
        raise unauthenticated("The identity token audience is invalid.")
    iss = claims.get("iss")
    expected = f"https://securetoken.google.com/{settings.firebase_project_id}"
    if iss != expected:
        raise unauthenticated("The identity token issuer is invalid.")
    return claims


async def _google_certs() -> dict[str, Any]:
    global _certs_at
    now = time.time()
    if _certs and now - _certs_at < 3600:
        return _certs
    url = "https://www.googleapis.com/robot/v1/metadata/x509/securetoken@system.gserviceaccount.com"
    async with httpx.AsyncClient(timeout=10) as client:
        response = await client.get(url)
        response.raise_for_status()
        data = response.json()
    if not isinstance(data, dict):
        raise unauthenticated("Could not load identity keys.")
    _certs.clear()
    _certs.update(data)
    _certs_at = now
    return _certs
