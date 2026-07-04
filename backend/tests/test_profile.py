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
