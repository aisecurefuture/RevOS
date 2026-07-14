"""Platform super-admin console + login lockout (env-allowlist gated)."""

from __future__ import annotations

import pytest


async def _register(api, email="user@test.com", pw="PassWord1234", name="User"):
    r = await api.post("/api/auth/register", json={"email": email, "password": pw, "full_name": name})
    assert r.status_code == 201, r.text
    return {"X-CSRF-Token": r.json()["csrf_token"]}


def _make_admin(monkeypatch, *emails):
    from app.config import settings as app_settings
    monkeypatch.setattr(app_settings, "platform_admin_emails", ",".join(emails))


# ---------------------------------------------------------------------------
# Access gate
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_non_platform_admin_is_forbidden(api):
    h = await _register(api, "nobody@test.com")
    assert (await api.get("/api/admin/accounts", headers=h)).status_code == 403


@pytest.mark.asyncio
async def test_platform_admin_via_env_allowlist(api, monkeypatch):
    _make_admin(monkeypatch, "boss@test.com")
    h = await _register(api, "boss@test.com")
    r = await api.get("/api/admin/accounts", headers=h)
    assert r.status_code == 200
    # /me reflects platform-admin status.
    me = (await api.get("/api/auth/me", headers=h)).json()
    assert me["is_platform_admin"] is True


@pytest.mark.asyncio
async def test_allowlist_is_case_insensitive(api, monkeypatch):
    _make_admin(monkeypatch, "Boss@Test.com")
    h = await _register(api, "boss@test.com")
    assert (await api.get("/api/admin/accounts", headers=h)).status_code == 200


# ---------------------------------------------------------------------------
# Admin operations
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_create_tenant_and_list(api, monkeypatch):
    _make_admin(monkeypatch, "boss@test.com")
    h = await _register(api, "boss@test.com")
    r = await api.post("/api/admin/accounts", headers=h, json={
        "name": "Acme Corp", "lead_email": "lead@acme.com",
    })
    assert r.status_code == 201, r.text
    assert r.json()["invited"] is True  # new lead → invited

    accounts = (await api.get("/api/admin/accounts", headers=h)).json()
    assert any(a["name"] == "Acme Corp" for a in accounts)


@pytest.mark.asyncio
async def test_disable_and_enable_account_blocks_members(api, make_client, monkeypatch):
    _make_admin(monkeypatch, "boss@test.com")
    boss = await make_client()
    member = await make_client()
    hb = await _register(boss, "boss@test.com")

    # A normal user with their own account.
    hm = await _register(member, "member@test.com")
    accts = (await member.get("/api/accounts", headers=hm)).json()
    acct_id = accts[0]["account"]["id"]

    # Boss disables it → member can no longer act under it.
    d = await boss.post(f"/api/admin/accounts/{acct_id}/disable", headers=hb, json={"reason": "abuse"})
    assert d.status_code == 200 and d.json()["disabled"] is True
    blocked = await member.get("/api/brands", headers=hm)
    assert blocked.status_code == 401

    # Re-enable → member works again.
    await boss.post(f"/api/admin/accounts/{acct_id}/enable", headers=hb)
    assert (await member.get("/api/brands", headers=hm)).status_code == 200


@pytest.mark.asyncio
async def test_disable_user_and_unlock(api, monkeypatch):
    _make_admin(monkeypatch, "boss@test.com")
    # Register victim FIRST; register boss LAST so the boss session is active
    # (both share one client's cookie jar).
    await _register(api, "victim@test.com")
    h = await _register(api, "boss@test.com")
    users = (await api.get("/api/admin/users", headers=h)).json()
    vid = next(u["id"] for u in users if u["email"] == "victim@test.com")

    assert (await api.post(f"/api/admin/users/{vid}/disable", headers=h)).status_code == 200
    users = (await api.get("/api/admin/users", headers=h)).json()
    assert next(u["is_active"] for u in users if u["id"] == vid) is False
    assert (await api.post(f"/api/admin/users/{vid}/unlock", headers=h)).status_code == 200
    assert (await api.post(f"/api/admin/users/{vid}/enable", headers=h)).status_code == 200


# ---------------------------------------------------------------------------
# Login lockout
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_login_locks_after_repeated_failures_then_unlock(api, monkeypatch):
    from app.config import settings as app_settings
    monkeypatch.setattr(app_settings, "login_max_failed_attempts", 3)
    _make_admin(monkeypatch, "boss@test.com")

    await _register(api, "target@test.com", pw="RightPass1234")
    for _ in range(3):
        r = await api.post("/api/auth/login", json={"email": "target@test.com", "password": "wrong"})
        assert r.status_code == 401

    # Now locked — even the CORRECT password is refused.
    locked = await api.post("/api/auth/login", json={"email": "target@test.com", "password": "RightPass1234"})
    assert locked.status_code == 401
    assert "lock" in locked.json()["error"]["message"].lower()

    # A platform admin unlocks, and the correct password works again.
    hb = await _register(api, "boss@test.com")
    users = (await api.get("/api/admin/users", headers=hb)).json()
    tid = next(u["id"] for u in users if u["email"] == "target@test.com")
    assert next(u["locked"] for u in users if u["id"] == tid) is True
    await api.post(f"/api/admin/users/{tid}/unlock", headers=hb)
    ok = await api.post("/api/auth/login", json={"email": "target@test.com", "password": "RightPass1234"})
    assert ok.status_code == 200


@pytest.mark.asyncio
async def test_successful_login_resets_failure_counter(api, monkeypatch):
    from app.config import settings as app_settings
    monkeypatch.setattr(app_settings, "login_max_failed_attempts", 3)
    await _register(api, "reset@test.com", pw="RightPass1234")

    await api.post("/api/auth/login", json={"email": "reset@test.com", "password": "wrong"})
    await api.post("/api/auth/login", json={"email": "reset@test.com", "password": "wrong"})
    # Correct login resets the counter…
    assert (await api.post("/api/auth/login", json={"email": "reset@test.com", "password": "RightPass1234"})).status_code == 200
    # …so two more failures don't lock (counter started fresh).
    await api.post("/api/auth/login", json={"email": "reset@test.com", "password": "wrong"})
    await api.post("/api/auth/login", json={"email": "reset@test.com", "password": "wrong"})
    assert (await api.post("/api/auth/login", json={"email": "reset@test.com", "password": "RightPass1234"})).status_code == 200
