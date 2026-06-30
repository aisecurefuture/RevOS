"""Security response headers middleware.

Baked in from day one (OWASP "Security Misconfiguration"). Applies a strict
set of headers to every response. The CSP is intentionally tight for the JSON
API; hosted landing pages (Module 6) relax it per-route as needed.
"""

from __future__ import annotations

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from app.config import settings


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next) -> Response:
        response = await call_next(request)
        headers = response.headers
        headers.setdefault("X-Content-Type-Options", "nosniff")
        headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
        headers.setdefault(
            "Permissions-Policy", "geolocation=(), microphone=(), camera=()"
        )
        # Public rendered pages (landing pages, embeddable forms) set their own
        # frame/CSP policy — an embeddable form must be iframe-able. The strict
        # default-deny policy below applies to the JSON API only.
        if not request.url.path.startswith("/api/public/"):
            headers.setdefault("X-Frame-Options", "DENY")
            headers.setdefault(
                "Content-Security-Policy",
                "default-src 'none'; frame-ancestors 'none'; base-uri 'none'",
            )
        # HSTS only when serving over HTTPS in production.
        if settings.is_production:
            headers.setdefault(
                "Strict-Transport-Security",
                "max-age=63072000; includeSubDomains; preload",
            )
        return response
