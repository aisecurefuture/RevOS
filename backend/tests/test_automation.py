"""Auto-approve autopilot — endpoint + beat sweeper (P3-M7).

Verifies the owner-only toggle, that the sweep executes pending approvals for
hands-off accounts (reusing the real publish path, mocked at the edges), and
that a lapsed window disables itself without approving anything.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from unittest.mock import AsyncMock, patch

import pytest


async def _register_owner(api, email="owner@test.com"):
    r = await api.post("/api/auth/register", json={
        "email": email, "password": "OwnerPass123", "full_name": "Owner",
    })
    assert r.status_code == 201, r.text
    return {"X-CSRF-Token": r.json()["csrf_token"]}


async def _seed_pending_social_approval(api, async_session_factory, headers):
    """Create a facebook post + connection and submit it → pending approval.
    Returns (account_id, brand_id, post_id, user_id)."""
    from app.models.social import SocialPost
    from app.models.social_connection import SocialConnection, SocialConnectionStatus

    me = (await api.get("/api/auth/me", headers=headers)).json()
    user_id = uuid.UUID(me["id"])
    bid = (await api.post("/api/brands", headers=headers, json={"name": "B"})).json()["id"]
    post = (await api.post("/api/social/posts", headers=headers, json={
        "brand_id": bid, "platform": "facebook", "caption": "Hi",
    })).json()

    async with async_session_factory() as s:
        sp = await s.get(SocialPost, uuid.UUID(post["id"]))
        account_id = sp.account_id
        s.add(SocialConnection(
            account_id=account_id, platform="facebook", external_id="ext-1",
            display_name="Page", status=SocialConnectionStatus.active,
            token_ref="revos/x", connected_by=user_id,
        ))
        await s.commit()

    assert (await api.post(f"/api/social/posts/{post['id']}/submit", headers=headers)).status_code == 200
    return account_id, bid, post["id"], user_id


# ---------------------------------------------------------------------------
# Endpoint
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_auto_approve_enable_disable(api):
    h = await _register_owner(api)

    # Enable with a fixed window.
    r = await api.post("/api/automation/auto-approve", headers=h,
                       json={"enabled": True, "duration_hours": 24})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["enabled"] is True and body["until"] and body["indefinite"] is False

    # Enable indefinitely (no duration).
    r2 = await api.post("/api/automation/auto-approve", headers=h, json={"enabled": True})
    assert r2.json()["indefinite"] is True and r2.json()["until"] is None

    # Off.
    r3 = await api.post("/api/automation/auto-approve", headers=h, json={"enabled": False})
    assert r3.json()["enabled"] is False

    # GET reflects the persisted state.
    assert (await api.get("/api/automation/auto-approve", headers=h)).json()["enabled"] is False


# ---------------------------------------------------------------------------
# Sweeper
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_sweep_publishes_pending_when_enabled(api, async_session_factory):
    from app.models.account import Account
    from app.services import automation_service
    from app.services.social import meta as meta_client

    h = await _register_owner(api)
    account_id, bid, post_id, user_id = await _seed_pending_social_approval(api, async_session_factory, h)

    # Turn on auto-approve for the account.
    async with async_session_factory() as s:
        acct = await s.get(Account, account_id)
        acct.auto_approve_enabled = True
        acct.auto_approve_set_by = user_id
        s.add(acct)
        await s.commit()

    # Run the sweep with the token + platform adapter mocked.
    with (
        patch("app.services.social_connection_service.secrets_service.get_secret",
              AsyncMock(return_value={"access_token": "tok", "page_id": "pg-1"})),
        patch.object(meta_client, "publish_to_page",
                     AsyncMock(return_value=meta_client.PublishResult(external_id="pg-1_1"))),
    ):
        async with async_session_factory() as s:
            stats = await automation_service.run_auto_approvals(s)
            await s.commit()

    assert stats["approved"] == 1
    posts = (await api.get(f"/api/social/posts?brand_id={bid}", headers=h)).json()
    assert posts[0]["state"] == "published"
    assert posts[0]["external_post_id"] == "pg-1_1"


@pytest.mark.asyncio
async def test_sweep_disables_expired_window_without_approving(api, async_session_factory):
    from app.models.account import Account
    from app.services import automation_service

    h = await _register_owner(api)
    account_id, bid, post_id, user_id = await _seed_pending_social_approval(api, async_session_factory, h)

    # Enabled, but the window already lapsed.
    async with async_session_factory() as s:
        acct = await s.get(Account, account_id)
        acct.auto_approve_enabled = True
        acct.auto_approve_until = datetime(2000, 1, 1)  # naive UTC, in the past
        acct.auto_approve_set_by = user_id
        s.add(acct)
        await s.commit()

    async with async_session_factory() as s:
        stats = await automation_service.run_auto_approvals(s)
        await s.commit()

    assert stats["expired"] == 1
    assert stats["approved"] == 0

    # Setting is now off, and the post is untouched (still pending review).
    async with async_session_factory() as s:
        acct = await s.get(Account, account_id)
        assert acct.auto_approve_enabled is False
    posts = (await api.get(f"/api/social/posts?brand_id={bid}", headers=h)).json()
    assert posts[0]["state"] == "needs_review"
