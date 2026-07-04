"""Phase 2 M2 — optional TOTP 2FA: enroll, two-step login, recovery codes."""

from __future__ import annotations

import pyotp
import pytest


async def _register(client, email="tf@test.com", pw="PassWord1234"):
    r = await client.post(
        "/api/auth/register", json={"email": email, "password": pw, "full_name": "TF"}
    )
    assert r.status_code == 201, r.text
    return {"X-CSRF-Token": r.json()["csrf_token"]}


async def _enroll(api, h):
    """Enroll in 2FA; return (secret, recovery_codes)."""
    setup = (await api.post("/api/auth/2fa/setup", headers=h)).json()
    secret = setup["secret"]
    assert setup["otpauth_uri"].startswith("otpauth://totp/")
    code = pyotp.TOTP(secret).now()
    verify = await api.post("/api/auth/2fa/verify", headers=h, json={"code": code})
    assert verify.status_code == 200, verify.text
    codes = verify.json()["recovery_codes"]
    assert len(codes) == 10
    return secret, codes


@pytest.mark.asyncio
async def test_enroll_then_login_requires_second_factor(api):
    h = await _register(api, "a@test.com")
    secret, _ = await _enroll(api, h)
    assert (await api.get("/api/auth/me", headers=h)).json()["totp_enabled"] is True

    # Password alone no longer yields a session — it returns a challenge.
    r = await api.post("/api/auth/login", json={"email": "a@test.com", "password": "PassWord1234"})
    assert r.status_code == 200
    body = r.json()
    assert body.get("twofa_required") is True and body.get("pending_token")
    assert "csrf_token" not in body  # no session issued yet

    # Wrong code is rejected.
    bad = await api.post(
        "/api/auth/2fa/login",
        json={"pending_token": body["pending_token"], "code": "000000"},
    )
    assert bad.status_code == 401

    # Correct TOTP completes the login.
    ok = await api.post(
        "/api/auth/2fa/login",
        json={"pending_token": body["pending_token"], "code": pyotp.TOTP(secret).now()},
    )
    assert ok.status_code == 200, ok.text
    assert ok.json()["user"]["totp_enabled"] is True


@pytest.mark.asyncio
async def test_recovery_code_works_once(api):
    h = await _register(api, "r@test.com")
    _, codes = await _enroll(api, h)
    login = (
        await api.post("/api/auth/login", json={"email": "r@test.com", "password": "PassWord1234"})
    ).json()

    # A recovery code completes login...
    first = await api.post(
        "/api/auth/2fa/login",
        json={"pending_token": login["pending_token"], "code": codes[0]},
    )
    assert first.status_code == 200, first.text

    # ...but it is single-use: a fresh challenge + the same code fails.
    login2 = (
        await api.post("/api/auth/login", json={"email": "r@test.com", "password": "PassWord1234"})
    ).json()
    reuse = await api.post(
        "/api/auth/2fa/login",
        json={"pending_token": login2["pending_token"], "code": codes[0]},
    )
    assert reuse.status_code == 401


@pytest.mark.asyncio
async def test_twofa_account_guard_blocks_after_budget():
    """The per-account 2FA guard caps failed attempts independent of source IP."""
    from app.core import rate_limit as rl

    rl.state.enabled = True
    rl.reset_limits()
    try:
        key = "acct-under-attack"
        assert rl.twofa_account_allowed(key) is True
        # Burn the whole budget (config default: 10 per 5 minutes) with failures.
        for _ in range(10):
            rl.record_twofa_failure(key)
        # This account is now locked out...
        assert rl.twofa_account_allowed(key) is False
        # ...but a different account is unaffected (per-account, not global).
        assert rl.twofa_account_allowed("innocent-bystander") is True
    finally:
        rl.state.enabled = False
        rl.reset_limits()


@pytest.mark.asyncio
async def test_disable_requires_password_and_code(api):
    h = await _register(api, "d@test.com")
    secret, _ = await _enroll(api, h)

    # Wrong password → refused.
    bad = await api.post(
        "/api/auth/2fa/disable", headers=h,
        json={"password": "WrongPass123", "code": pyotp.TOTP(secret).now()},
    )
    assert bad.status_code == 401

    # Correct password + code → disabled, login no longer challenges.
    ok = await api.post(
        "/api/auth/2fa/disable", headers=h,
        json={"password": "PassWord1234", "code": pyotp.TOTP(secret).now()},
    )
    assert ok.status_code == 200, ok.text
    login = (
        await api.post("/api/auth/login", json={"email": "d@test.com", "password": "PassWord1234"})
    ).json()
    assert "twofa_required" not in login and login.get("csrf_token")
