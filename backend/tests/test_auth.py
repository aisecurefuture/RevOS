"""Auth flow integration tests (Module 3) — async via httpx ASGI."""

from __future__ import annotations

import pytest
from app.core.rate_limit import reset_limits
from app.core.rate_limit import state as rl_state
from app.core.security import ACCESS_COOKIE, CSRF_COOKIE


async def _login(api, creds):
    return await api.post("/api/auth/login", json=creds)


@pytest.mark.asyncio
async def test_login_success_sets_cookies(api, owner_credentials):
    resp = await _login(api, owner_credentials)
    assert resp.status_code == 200
    body = resp.json()
    assert body["user"]["email"] == owner_credentials["email"]
    assert body["user"]["role"] == "owner"
    assert body["csrf_token"]
    assert ACCESS_COOKIE in resp.cookies
    assert CSRF_COOKIE in resp.cookies


@pytest.mark.asyncio
async def test_login_wrong_password_401(api, owner_credentials):
    resp = await _login(api, {"email": owner_credentials["email"], "password": "WrongPass123"})
    assert resp.status_code == 401
    assert resp.json()["error"]["code"] == "unauthorized"


@pytest.mark.asyncio
async def test_me_requires_auth(api):
    resp = await api.get("/api/auth/me")
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_me_after_login(api, owner_credentials):
    await _login(api, owner_credentials)
    resp = await api.get("/api/auth/me")
    assert resp.status_code == 200
    assert resp.json()["email"] == owner_credentials["email"]


@pytest.mark.asyncio
async def test_logout_requires_csrf_then_clears(api, owner_credentials):
    login = await _login(api, owner_credentials)
    csrf = login.json()["csrf_token"]

    # Without CSRF header -> blocked.
    blocked = await api.post("/api/auth/logout")
    assert blocked.status_code == 403
    assert blocked.json()["error"]["code"] == "csrf_failed"

    # With CSRF header -> succeeds and clears the session.
    ok = await api.post("/api/auth/logout", headers={"X-CSRF-Token": csrf})
    assert ok.status_code == 200
    after = await api.get("/api/auth/me")
    assert after.status_code == 401


@pytest.mark.asyncio
async def test_refresh_issues_new_session(api, owner_credentials):
    await _login(api, owner_credentials)
    resp = await api.post("/api/auth/refresh")
    assert resp.status_code == 200
    assert resp.json()["user"]["email"] == owner_credentials["email"]


@pytest.mark.asyncio
async def test_password_change_and_relogin(api, owner_credentials):
    login = await _login(api, owner_credentials)
    csrf = login.json()["csrf_token"]
    resp = await api.post(
        "/api/auth/password",
        headers={"X-CSRF-Token": csrf},
        json={"current_password": owner_credentials["password"], "new_password": "BrandNewPass456"},
    )
    assert resp.status_code == 200
    # Old password no longer works; new one does.
    assert (await _login(api, owner_credentials)).status_code == 401
    relog = await _login(api, {"email": owner_credentials["email"], "password": "BrandNewPass456"})
    assert relog.status_code == 200


@pytest.mark.asyncio
async def test_password_change_invalidates_existing_session(api, owner_credentials):
    """A token minted before a password change is rejected (token_version bump)."""
    login = await _login(api, owner_credentials)
    csrf = login.json()["csrf_token"]
    assert (await api.get("/api/auth/me")).status_code == 200

    changed = await api.post(
        "/api/auth/password", headers={"X-CSRF-Token": csrf},
        json={"current_password": owner_credentials["password"], "new_password": "RotatedPass999"})
    assert changed.status_code == 200
    # The still-held access cookie is now stale and rejected.
    assert (await api.get("/api/auth/me")).status_code == 401


@pytest.mark.asyncio
async def test_login_rate_limited(api, owner_credentials):
    """With the limiter enabled, repeated logins eventually return 429."""
    rl_state.enabled = True
    reset_limits()
    try:
        statuses = []
        for _ in range(8):
            r = await _login(api, {"email": owner_credentials["email"], "password": "WrongPass123"})
            statuses.append(r.status_code)
        assert 429 in statuses, f"expected a 429 in {statuses}"
        assert statuses.count(401) <= 5
    finally:
        rl_state.enabled = False
        reset_limits()
