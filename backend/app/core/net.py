"""Network helpers — trustworthy client IP resolution.

X-Forwarded-For is attacker-controlled unless the app sits behind a known proxy,
so it is only honored when ``trust_proxy`` is enabled. Otherwise the real peer
address (``request.client.host``) is used. This prevents per-IP rate limits from
being trivially bypassed by spoofing the header.
"""

from __future__ import annotations

from starlette.requests import Request

from app.config import settings


def client_ip(request: Request) -> str | None:
    if settings.trust_proxy:
        forwarded = request.headers.get("x-forwarded-for")
        if forwarded:
            # Right-most entries are added by closer (more trusted) proxies; we
            # take the first (original client) since we trust the chain.
            return forwarded.split(",")[0].strip()[:64]
    return request.client.host if request.client else None
