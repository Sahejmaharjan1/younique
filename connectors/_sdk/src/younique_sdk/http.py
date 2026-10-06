from __future__ import annotations

import ipaddress
import socket
from collections.abc import Callable
from typing import Any
from urllib.parse import urljoin, urlparse

import httpx

from younique_sdk.errors import ConnectorError

Resolver = Callable[[str], list[str]]

BLOCKED_NETWORKS = [
    ipaddress.ip_network("0.0.0.0/8"),
    ipaddress.ip_network("10.0.0.0/8"),
    ipaddress.ip_network("127.0.0.0/8"),
    ipaddress.ip_network("169.254.0.0/16"),
    ipaddress.ip_network("172.16.0.0/12"),
    ipaddress.ip_network("192.168.0.0/16"),
    ipaddress.ip_network("100.64.0.0/10"),
    ipaddress.ip_network("::1/128"),
    ipaddress.ip_network("fc00::/7"),
    ipaddress.ip_network("fe80::/10"),
    ipaddress.ip_network("::ffff:0:0/96"),
]


def default_resolver(host: str) -> list[str]:
    try:
        infos = socket.getaddrinfo(host, None)
    except socket.gaierror as exc:
        raise ConnectorError("connector_unavailable", f"Could not resolve {host}") from exc
    found: list[str] = []
    for info in infos:
        address = str(info[4][0])
        if address not in found:
            found.append(address)
    return found


def ip_is_blocked(value: str) -> bool:
    try:
        parsed = ipaddress.ip_address(value)
    except ValueError:
        return True
    if parsed.is_private or parsed.is_loopback or parsed.is_link_local or parsed.is_reserved or parsed.is_multicast or parsed.is_unspecified:
        return True
    return any(parsed in network for network in BLOCKED_NETWORKS)


def assert_public_host(host: str, resolver: Resolver) -> None:
    if host in {"localhost", "metadata.google.internal"}:
        raise ConnectorError("connector_permission_denied", f"Host {host} is blocked")
    try:
        ipaddress.ip_address(host)
    except ValueError:
        pass
    else:
        if ip_is_blocked(host):
            raise ConnectorError("connector_permission_denied", f"Host {host} is blocked")
    addresses = resolver(host)
    if not addresses:
        raise ConnectorError("connector_unavailable", f"Host {host} did not resolve")
    for address in addresses:
        if ip_is_blocked(address):
            raise ConnectorError(
                "connector_permission_denied",
                f"Host {host} resolves to a blocked address",
            )


class SafeHttp:
    def __init__(
        self,
        *,
        allowlist: list[str] | None = None,
        resolver: Resolver | None = None,
        client: httpx.AsyncClient | None = None,
        timeout: float = 20.0,
    ) -> None:
        self.allowlist = [item.lower() for item in (allowlist or [])]
        self.resolver = resolver or default_resolver
        self.timeout = timeout
        self._client = client

    def _host_allowed(self, host: str) -> None:
        if not self.allowlist:
            raise ConnectorError("connector_permission_denied", "No hosts are allowlisted")
        lowered = host.lower()
        if lowered not in self.allowlist and not any(
            lowered == item or lowered.endswith("." + item) for item in self.allowlist
        ):
            raise ConnectorError("connector_permission_denied", f"Host {host} is not allowlisted")

    async def request(
        self,
        method: str,
        url: str,
        *,
        headers: dict[str, str] | None = None,
        json: dict[str, Any] | None = None,
        content: bytes | None = None,
    ) -> httpx.Response:
        current = url
        for _ in range(5):
            parsed = urlparse(current)
            if parsed.scheme not in {"https", "http"} or not parsed.hostname:
                raise ConnectorError("connector_permission_denied", "URL is not allowed")
            self._host_allowed(parsed.hostname)
            assert_public_host(parsed.hostname, self.resolver)
            client = self._client or httpx.AsyncClient(timeout=self.timeout, follow_redirects=False)
            owned = self._client is None
            try:
                response = await client.request(
                    method,
                    current,
                    headers=headers,
                    json=json,
                    content=content,
                )
            finally:
                if owned:
                    await client.aclose()
            if response.status_code in {301, 302, 303, 307, 308}:
                location = response.headers.get("location")
                if not location:
                    return response
                nxt = urljoin(current, location)
                next_host = urlparse(nxt).hostname or ""
                if next_host.lower() != parsed.hostname.lower():
                    raise ConnectorError(
                        "connector_permission_denied",
                        "Cross-host redirects are refused",
                    )
                assert_public_host(next_host, self.resolver)
                current = nxt
                method = "GET" if response.status_code == 303 else method
                json = None
                content = None
                continue
            return response
        raise ConnectorError("connector_unavailable", "Too many redirects")
