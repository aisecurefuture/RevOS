"""Phase 2 M2 — email verification and profile editing."""

from __future__ import annotations

import pytest

from app.services.verification_service import make_verification_token


# --- helpers ----------------------------------------------------------------

async def _register(client, email, pw="PassWord1234", name="Test User"):
    r = await client.post(
        "/api/auth/register", json={"email": email, "password": pw, "full_name": name}
    )
    assert r.status_code == 201, r.text
    data = r.json()
    return {"X-CSRF-Token": data["csrf_token"]}, data


# --- tests ------------------------------------------------------------------

@pytest.mark.asyncio
async def test_email_not_verified_on_register(api):
    """Newly registered users start with email_verified=False."""
    h, reg = await _register(api, "unverified@profile.com")
    assert reg["user"]["email_verified"] is False

    me = (await api.get("/api/auth/me", headers=h)).json()
    assert me["email_verified"] is False


@pytest.mark.asyncio
async def test_verify_email_token(api, async_session_factory):
    """GET /api/auth/verify-email?token= marks the user as verified."""
    h, _ = await _register(api, "verify@profile.com")

    # Generate the verification token for this user (same as what would be emailed)
    async with async_session_factory() as session:
        from sqlmodel import select
        from app.models.user import AdminUser
        res = await session.execute(
            select(AdminUser).where(AdminUser.email == "verify@profile.com")
        )
        user = res.scalar_one()
        token = make_verification_token(user)

    r = await api.get(f"/api/auth/verify-email?token={token}")
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "verified"

    me = (await api.get("/api/auth/me", headers=h)).json()
    assert me["email_verified"] is True


@pytest.mark.asyncio
async def test_update_profile(api):
    """PATCH /api/auth/me updates name, timezone, and avatar_url."""
    h, _ = await _register(api, "profile@profile.com", name="Old Name")

    r = await api.patch(
        "/api/auth/me",
        json={"full_name": "New Name", "timezone": "America/Chicago", "avatar_url": "https://example.com/avatar.png"},
        headers=h,
    )
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["full_name"] == "New Name"
    assert data["timezone"] == "America/Chicago"
    assert data["avatar_url"] == "https://example.com/avatar.png"

    # Persists across a GET /me
    me = (await api.get("/api/auth/me", headers=h)).json()
    assert me["full_name"] == "New Name"
    assert me["timezone"] == "America/Chicago"


@pytest.mark.asyncio
async def test_resend_verification(api):
    """POST /api/auth/verify-email/resend works when unverified."""
    h, _ = await _register(api, "resend@profile.com")
    r = await api.post("/api/auth/verify-email/resend", headers=h)
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "sent"


# ---------------------------------------------------------------------------
# Verified-email gate on actions with external reach (P3)
# ---------------------------------------------------------------------------

async def _verify(api, async_session_factory, email):
    from sqlmodel import select
    from app.models.user import AdminUser

    async with async_session_factory() as session:
        res = await session.execute(select(AdminUser).where(AdminUser.email == email))
        user = res.scalar_one()
        token = make_verification_token(user)
    r = await api.get(f"/api/auth/verify-email?token={token}")
    assert r.status_code == 200, r.text


@pytest.mark.asyncio
async def test_unverified_user_blocked_from_inviting_a_teammate(api):
    h, _ = await _register(api, "unverified-invite@profile.com")
    team = (await api.post("/api/accounts", headers=h, json={"name": "Team"})).json()

    r = await api.post(f"/api/accounts/{team['id']}/invitations", headers=h, json={
        "email": "someone@example.com", "role": "editor",
    })
    assert r.status_code == 403, r.text
    assert r.json()["error"]["code"] == "email_not_verified"


@pytest.mark.asyncio
async def test_verified_user_can_invite_a_teammate(api, async_session_factory):
    h, _ = await _register(api, "verified-invite@profile.com")
    await _verify(api, async_session_factory, "verified-invite@profile.com")

    team = (await api.post("/api/accounts", headers=h, json={"name": "Team"})).json()
    r = await api.post(f"/api/accounts/{team['id']}/invitations", headers=h, json={
        "email": "someone@example.com", "role": "editor",
    })
    assert r.status_code == 201, r.text


@pytest.mark.asyncio
async def test_unverified_user_blocked_from_connect_url(api):
    h, _ = await _register(api, "unverified-connect@profile.com")
    r = await api.get("/api/social/connections/connect-url?platform=facebook", headers=h)
    assert r.status_code == 403, r.text
    assert r.json()["error"]["code"] == "email_not_verified"


@pytest.mark.asyncio
async def test_unverified_user_blocked_from_approving(api, async_session_factory):
    """A pending approval must not be approvable (i.e. published) by an
    unverified user, even one with the admin role otherwise required."""
    from sqlmodel import select
    from app.models.account import Account
    from app.models.approval import ApprovalAction, ApprovalRequest, ApprovalStatus
    from app.models.user import AdminUser

    h, reg = await _register(api, "unverified-approve@profile.com")

    async with async_session_factory() as s:
        res = await s.execute(select(AdminUser).where(AdminUser.email == "unverified-approve@profile.com"))
        user = res.scalar_one()
        acct = (await s.execute(
            select(Account).where(Account.owner_user_id == user.id)
        )).scalars().first()
        approval = ApprovalRequest(
            account_id=acct.id, action_type=ApprovalAction.campaign_send,
            entity_type="test", entity_id=user.id, title="Test",
            requested_by_user_id=user.id, status=ApprovalStatus.pending,
        )
        s.add(approval)
        await s.commit()
        await s.refresh(approval)
        approval_id = approval.id

    r = await api.post(f"/api/approvals/{approval_id}/approve", headers=h)
    assert r.status_code == 403, r.text
    assert r.json()["error"]["code"] == "email_not_verified"
