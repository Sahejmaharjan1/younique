from __future__ import annotations

import time
from typing import Any

import httpx
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import padding
from cryptography.x509 import load_pem_x509_certificate

from younique.core.config import Settings
from younique.core.errors import unauthenticated
from younique.core.firebase import _b64url

_certs: dict[str, Any] = {}


async def verify_internal_caller(authorization: str | None, settings: Settings) -> None:
    if not authorization or not authorization.startswith("Bearer "):
        raise unauthenticated("Internal caller token is missing.")
    token = authorization.removeprefix("Bearer ").strip()
    if settings.oidc_emulator:
        if token != settings.dev_internal_token:
            raise unauthenticated("Internal caller token is invalid.")
        return
    claims = await _verify_google_oidc(token)
    aud = claims.get("aud")
    if aud != settings.internal_oidc_audience:
        raise unauthenticated("Internal caller audience is invalid.")
    exp = claims.get("exp")
    if isinstance(exp, int) and exp < int(time.time()):
        raise unauthenticated("Internal caller token is expired.")


async def _verify_google_oidc(token: str) -> dict[str, Any]:
    header_raw, payload_raw, signature = token.split(".")
    header = __import__("json").loads(_b64url(header_raw))
    kid = header.get("kid")
    if not _certs:
        async with httpx.AsyncClient(timeout=10) as client:
            response = await client.get("https://www.googleapis.com/oauth2/v3/certs")
            response.raise_for_status()
            body = response.json()
        for key in body.get("keys", []):
            if "kid" in key:
                _certs[key["kid"]] = key
    if kid not in _certs:
        raise unauthenticated("Internal caller key is unknown.")
    cert_pem = _certs[kid].get("x5c")
    if not cert_pem:
        raise unauthenticated("Internal caller certificate is missing.")
    pem = "-----BEGIN CERTIFICATE-----\n" + cert_pem[0] + "\n-----END CERTIFICATE-----\n"
    cert = load_pem_x509_certificate(pem.encode())
    public_key: Any = cert.public_key()
    public_key.verify(
        _b64url(signature),
        f"{header_raw}.{payload_raw}".encode(),
        padding.PKCS1v15(),
        hashes.SHA256(),
    )
    data = __import__("json").loads(_b64url(payload_raw))
    if not isinstance(data, dict):
        raise unauthenticated("Internal caller token is malformed.")
    return data
