"""SSRF protection for server-side URL fetches.

Any time the server fetches a user-supplied URL (link previews, outbound
webhooks, image imports) it must pass through ``validate_outbound_url``:
- scheme restricted to http/https,
- host must be on the configured allowlist (empty allowlist = deny all),
- every resolved IP must be public (blocks loopback/private/link-local/etc.),
  which defends against DNS-rebinding to internal addresses.
"""

from __future__ import annotations

import ipaddress
import socket
from urllib.parse import urlparse

from app.config import settings
from app.core.exceptions import RevOSError


class SSRFError(RevOSError):
    code = "ssrf_blocked"
    status_code = 400


def _is_public_ip(ip: str) -> bool:
    try:
        addr = ipaddress.ip_address(ip)
    except ValueError:
        return False
    return not (
        addr.is_private
        or addr.is_loopback
        or addr.is_link_local
        or addr.is_multicast
        or addr.is_reserved
        or addr.is_unspecified
    )


def validate_outbound_url(url: str) -> str:
    """Return the URL if safe to fetch server-side, else raise SSRFError."""
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"}:
        raise SSRFError("Only http(s) URLs may be fetched.")
    host = parsed.hostname
    if not host:
        raise SSRFError("URL has no host.")

    allowlist = settings.ssrf_allowed_host_list
    if not allowlist:
        raise SSRFError("Outbound fetches are disabled (empty SSRF allowlist).")
    if host.lower() not in allowlist:
        raise SSRFError(f"Host '{host}' is not on the outbound allowlist.")

    # Resolve and verify every A/AAAA record is a public address.
    try:
        infos = socket.getaddrinfo(host, parsed.port or (443 if parsed.scheme == "https" else 80))
    except socket.gaierror as exc:
        raise SSRFError(f"Could not resolve host '{host}'.") from exc
    for info in infos:
        ip = info[4][0]
        if not _is_public_ip(ip):
            raise SSRFError(f"Host '{host}' resolves to a non-public address.")
    return url
