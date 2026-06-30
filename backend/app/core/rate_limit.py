"""Rate limiting as a FastAPI dependency.

Implemented directly on the ``limits`` library (fixed-window, per-IP) rather
than slowapi's decorator, because that decorator rewrites the endpoint
signature and breaks FastAPI's body/dependency detection. Backed by Redis in
prod and in-memory in tests (``effective_rate_limit_storage``).
"""

from __future__ import annotations

from limits import parse
from limits.storage import storage_from_string
from limits.strategies import FixedWindowRateLimiter
from starlette.requests import Request

from app.config import settings
from app.core.exceptions import RevOSError
from app.core.net import client_ip


class RateLimitError(RevOSError):
    code = "rate_limited"
    status_code = 429


_storage = storage_from_string(settings.effective_rate_limit_storage)
_strategy = FixedWindowRateLimiter(_storage)


class _State:
    """Toggle used to disable limiting in tests."""

    enabled = True


state = _State()


def reset_limits() -> None:
    """Clear all counters (test isolation)."""
    try:
        _storage.reset()
    except (NotImplementedError, AttributeError):  # some backends lack reset
        pass


def rate_limit(name: str, limit: str):
    """Build a dependency enforcing ``limit`` (e.g. "5/minute") per client IP."""
    item = parse(limit)

    async def _dependency(request: Request) -> None:
        if not state.enabled:
            return
        if not _strategy.hit(item, name, client_ip(request) or "anonymous"):
            raise RateLimitError("Too many requests. Please slow down.")

    return _dependency


# Login throttle (credential-stuffing defense).
rate_limit_login = rate_limit("login", settings.login_rate_limit)
