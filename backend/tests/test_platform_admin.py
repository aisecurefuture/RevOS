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


# ---------------------------------------------------------------------------
# Email login OTP (anti-bot) + trusted device + register honeypot
# ---------------------------------------------------------------------------

def _enable_email_otp(monkeypatch):
    from app.config import settings as s
    monkeypatch.setattr(s, "login_email_otp", True)
    monkeypatch.setattr(s, "resend_api_key", "re_test")   # email_enabled needs a key…
    monkeypatch.setattr(s, "email_test_mode", False)      # …and not test mode


@pytest.mark.asyncio
async def test_email_otp_required_then_completes_and_trusts_device(api, monkeypatch):
    _enable_email_otp(monkeypatch)
    # Capture the emailed code instead of really sending.
    sent = {}
    from app.services import email_otp_service
    monkeypatch.setattr(email_otp_service, "send_transactional",
                        lambda **kw: sent.update(subject=kw["subject"]))

    await _register(api, "otp@test.com", pw="RightPass1234")
    # Fresh login (register auto-logged-in, but a new login triggers the code).
    r = await api.post("/api/auth/login", json={"email": "otp@test.com", "password": "RightPass1234"})
    assert r.status_code == 200
    assert r.json()["email_otp_required"] is True
    pending = r.json()["pending_token"]
    code = sent["subject"].split()[-1]  # "Your RevOS login code: 123456"

    bad = await api.post("/api/auth/login/email-otp", json={"pending_token": pending, "code": "000000"})
    assert bad.status_code == 401
    ok = await api.post("/api/auth/login/email-otp", json={"pending_token": pending, "code": code})
    assert ok.status_code == 200, ok.text
    assert ok.json()["user"]["email"] == "otp@test.com"

    # This browser is now trusted — a subsequent login skips the code.
    again = await api.post("/api/auth/login", json={"email": "otp@test.com", "password": "RightPass1234"})
    assert again.status_code == 200
    assert "email_otp_required" not in again.json()


@pytest.mark.asyncio
async def test_email_otp_inactive_without_email_delivery(api, monkeypatch):
    """Safety: with the flag on but email NOT configured, login must NOT
    require a code (else a broken mailer locks everyone out)."""
    from app.config import settings as s
    monkeypatch.setattr(s, "login_email_otp", True)
    monkeypatch.setattr(s, "resend_api_key", "")  # email disabled
    await _register(api, "safe@test.com", pw="RightPass1234")
    r = await api.post("/api/auth/login", json={"email": "safe@test.com", "password": "RightPass1234"})
    assert r.status_code == 200
    assert "email_otp_required" not in r.json()


@pytest.mark.asyncio
async def test_register_honeypot_blocks_bots(api):
    filled = await api.post("/api/auth/register", json={
        "email": "bot@test.com", "password": "PassWord1234", "full_name": "Bot",
        "website": "http://spam.example",  # bot filled the hidden field
    })
    assert filled.status_code == 401
    # A normal signup (no honeypot value) still works.
    clean = await api.post("/api/auth/register", json={
        "email": "human@test.com", "password": "PassWord1234", "full_name": "Human",
    })
    assert clean.status_code == 201


# ---------------------------------------------------------------------------
# Complimentary (comp) access — team bypasses the trial paywall
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_comp_access_bypasses_expired_trial(api, make_client, async_session_factory, monkeypatch):
    """Expired-trial account gets comp -> full access with unlimited-ish limits."""
    _make_admin(monkeypatch, "boss@comp.com")
    admin_h = await _register(api, "boss@comp.com")

    team = await make_client()
    r = await team.post("/api/auth/register", json={
        "email": "teammate@comp.com", "password": "PassWord1234", "full_name": "Teammate",
    })
    team_h = {"X-CSRF-Token": r.json()["csrf_token"]}

    # Expire the teammate's trial.
    import datetime
    import uuid as _uuid
    from sqlalchemy import select as sa_select
    from app.models.billing import Subscription
    accounts = (await team.get("/api/accounts", headers=team_h)).json()
    account_id = _uuid.UUID(accounts[0]["account"]["id"])
    async with async_session_factory() as s:
        sub = (await s.execute(sa_select(Subscription).where(Subscription.account_id == account_id))).scalar_one()
        sub.trial_ends_at = sub.trial_ends_at - datetime.timedelta(days=30) if sub.trial_ends_at else None
        s.add(sub)
        await s.commit()

    bs = (await team.get("/api/billing/status", headers=team_h)).json()
    assert bs["is_trial_expired"] is True
    assert bs["effective_plan"] is None  # locked

    # Admin grants comp.
    r = await api.post(f"/api/admin/accounts/{account_id}/comp", headers=admin_h, json={"enabled": True})
    assert r.status_code == 200, r.text
    assert r.json()["plan"] == "comp"
    assert r.json()["billing_status"] == "active"

    bs = (await team.get("/api/billing/status", headers=team_h)).json()
    assert bs["effective_plan"] == "comp"
    assert bs["is_trial_expired"] is False
    assert bs["limits"]["seats"] is None            # unlimited
    assert bs["limits"]["white_label"] is True
    assert bs["limits"]["emails_per_month"] == 5000  # shared-Resend cap still applies

    # Admin revokes -> locked again.
    r = await api.post(f"/api/admin/accounts/{account_id}/comp", headers=admin_h, json={"enabled": False})
    assert r.status_code == 200
    bs = (await team.get("/api/billing/status", headers=team_h)).json()
    assert bs["effective_plan"] is None


@pytest.mark.asyncio
async def test_comp_revoke_requires_comp_plan(api, monkeypatch):
    """Revoking comp on an account that isn't comp (e.g. still trialing) 409s."""
    _make_admin(monkeypatch, "boss2@comp.com")
    h = await _register(api, "boss2@comp.com")
    accounts = (await api.get("/api/admin/accounts", headers=h)).json()
    acct_id = accounts[0]["id"]
    r = await api.post(f"/api/admin/accounts/{acct_id}/comp", headers=h, json={"enabled": False})
    assert r.status_code == 409


@pytest.mark.asyncio
async def test_comp_requires_platform_admin(api, make_client):
    h = await _register(api, "pleb@comp.com")
    accounts = (await api.get("/api/accounts", headers=h)).json()
    acct_id = accounts[0]["account"]["id"]
    r = await api.post(f"/api/admin/accounts/{acct_id}/comp", headers=h, json={"enabled": True})
    assert r.status_code == 403
