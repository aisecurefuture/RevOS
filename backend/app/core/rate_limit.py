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

# Per-IP throttle for 2FA code entry on setup/disable flows.
rate_limit_2fa = rate_limit("2fa_ip", settings.twofa_rate_limit)


# --- Per-account 2FA brute-force guard --------------------------------------
# Keyed on the *account*, not the client IP, so an attacker rotating source IPs
# against a single victim is still capped. Only failed attempts consume the
# budget (a successful login must never lock a user out), so we peek with
# ``test`` on entry and ``hit`` only after a code is rejected.
_2fa_account_item = parse(settings.twofa_rate_limit)


def twofa_account_allowed(account_key: str) -> bool:
    """True while this account is still under its 2FA attempt budget."""
    if not state.enabled:
        return True
    return _strategy.test(_2fa_account_item, "2fa_account", account_key)


def record_twofa_failure(account_key: str) -> None:
    """Charge one failed 2FA attempt against the per-account budget."""
    if not state.enabled:
        return
    _strategy.hit(_2fa_account_item, "2fa_account", account_key)
