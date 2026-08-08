import hmac
import secrets
import time
from collections import defaultdict, deque
from collections.abc import Callable

from fastapi import HTTPException, Request, status
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import Response


def get_csrf_token(request: Request) -> str:
    token = request.session.get("csrf_token")
    if not token:
        token = secrets.token_urlsafe(32)
        request.session["csrf_token"] = token
    return token


async def verify_csrf(request: Request) -> None:
    expected = request.session.get("csrf_token", "")
    supplied = request.headers.get("X-CSRF-Token", "")
    content_type = request.headers.get("content-type", "")
    if not supplied and "application/x-www-form-urlencoded" in content_type:
        form = await request.form()
        supplied = str(form.get("csrf_token", ""))
    if not expected or not supplied or not hmac.compare_digest(expected, supplied):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Invalid CSRF token")


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        response = await call_next(request)
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; img-src 'self' data: https:; style-src 'self'; "
            "script-src 'self'; connect-src 'self'; frame-ancestors 'none'; base-uri 'self'; "
            "form-action 'self' https://checkout.stripe.com https://billing.stripe.com"
        )
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Permissions-Policy"] = (
            "camera=(), microphone=(), geolocation=(), publickey-credentials-get=(self)"
        )
        if request.url.scheme == "https":
            response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
        if request.url.path.startswith(("/app", "/deals", "/billing", "/settings")):
            response.headers["Cache-Control"] = "no-store"
        return response


class RateLimiter:
    """Small single-instance limiter; use the reverse proxy for distributed limits."""

    # Drained keys hold an empty deque forever otherwise, so a caller cycling
    # keys (a fresh IP or email per request) would grow this dict without bound
    # until the container is OOM-killed.
    SWEEP_INTERVAL = 500

    def __init__(self) -> None:
        self._hits: dict[str, deque[float]] = defaultdict(deque)
        self._calls_since_sweep = 0
        self._widest_window = 0

    def check(self, key: str, limit: int, window_seconds: int) -> None:
        now = time.monotonic()
        self._widest_window = max(self._widest_window, window_seconds)
        hits = self._hits[key]
        cutoff = now - window_seconds
        while hits and hits[0] < cutoff:
            hits.popleft()
        if len(hits) >= limit:
            raise HTTPException(status_code=429, detail="Too many requests. Try again shortly.")
        hits.append(now)
        self._calls_since_sweep += 1
        if self._calls_since_sweep >= self.SWEEP_INTERVAL:
            self._sweep(now)

    def _sweep(self, now: float) -> None:
        self._calls_since_sweep = 0
        horizon = now - self._widest_window
        for key in [key for key, hits in self._hits.items() if not hits or hits[-1] < horizon]:
            del self._hits[key]


rate_limiter = RateLimiter()


def client_key(request: Request, scope: str) -> str:
    # The app only trusts the socket peer. A trusted reverse proxy should enforce its own limits.
    host = request.client.host if request.client else "unknown"
    return f"{scope}:{host}"
