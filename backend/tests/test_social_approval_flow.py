"""Social post → approval queue → publish wiring (P2-M6).

Regression: a social post submitted for approval must appear in the shared
Approvals queue, and approving it must publish via the connected platform.
"""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, patch

import pytest
from sqlalchemy import select


async def _register_owner(api, async_session_factory):
    r = await api.post("/api/auth/register", json={
        "email": "owner@test.com", "password": "OwnerPass123", "full_name": "Owner",
    })
    assert r.status_code == 201, r.text
    from app.models.base import utcnow
    from app.models.user import AdminUser
    from sqlalchemy import select

    async with async_session_factory() as s:
        user = (await s.execute(select(AdminUser).where(AdminUser.email == "owner@test.com"))).scalar_one()
        user.email_verified_at = utcnow()
        s.add(user)
        await s.commit()
    return {"X-CSRF-Token": r.json()["csrf_token"]}


async def _seed(api, async_session_factory, headers, platform):
    """Create a brand + draft post, then seed an active connection on the same
    account (connections are normally created by the OAuth callback)."""
    from app.models.social import SocialPost
    from app.models.social_connection import SocialConnection, SocialConnectionStatus

    me = (await api.get("/api/auth/me", headers=headers)).json()
    user_id = uuid.UUID(me["id"])
    bid = (await api.post("/api/brands", headers=headers, json={"name": "Brand"})).json()["id"]
    post = (await api.post("/api/social/posts", headers=headers, json={
        "brand_id": bid, "platform": platform, "caption": "Hello from RevOS",
    })).json()

    async with async_session_factory() as s:
        sp = await s.get(SocialPost, uuid.UUID(post["id"]))
        account_id = sp.account_id
        conn = SocialConnection(
            account_id=account_id, platform=platform, external_id="ext-1",
            handle="acct", display_name="Acct", status=SocialConnectionStatus.active,
            token_ref=f"revos/accounts/{account_id}/social/{platform}/x",
            connected_by=user_id,
        )
        s.add(conn)
        await s.commit()
    return bid, post["id"]


@pytest.mark.asyncio
async def test_submit_appears_in_approvals_then_publishes(api, async_session_factory):
    h = await _register_owner(api, async_session_factory)
    bid, post_id = await _seed(api, async_session_factory, h, "facebook")

    # Submit for approval — no connection_id, auto-resolved from the platform.
    submit = await api.post(f"/api/social/posts/{post_id}/submit", headers=h)
    assert submit.status_code == 200, submit.text

    # It now shows in the shared approval queue.
    approvals = (await api.get("/api/approvals", headers=h)).json()
    social = [a for a in approvals if a["action_type"] == "social_publish"]
    assert len(social) == 1, f"expected one social_publish approval, got {approvals}"
    approval_id = social[0]["id"]
    assert "facebook" in social[0]["title"].lower()

    # And the post reflects the pending review.
    posts = (await api.get(f"/api/social/posts?brand_id={bid}", headers=h)).json()
    assert posts[0]["state"] == "needs_review"

    # Approving publishes via the platform adapter (token + adapter mocked).
    from app.services.social import meta as meta_client
    with (
        patch("app.services.social_connection_service.secrets_service.get_secret",
              AsyncMock(return_value={"access_token": "tok", "page_id": "pg-1"})),
        patch.object(meta_client, "publish_to_page",
                     AsyncMock(return_value=meta_client.PublishResult(external_id="pg-1_99"))),
    ):
        approve = await api.post(f"/api/approvals/{approval_id}/approve", headers=h)
        assert approve.status_code == 200, approve.text
        assert approve.json()["status"] == "approved"

    # Post is published with the external id from the platform.
    posts = (await api.get(f"/api/social/posts?brand_id={bid}", headers=h)).json()
    assert posts[0]["state"] == "published"
    assert posts[0]["external_post_id"] == "pg-1_99"


@pytest.mark.asyncio
async def test_submit_without_connection_is_rejected(api, async_session_factory):
    """With no connected account for the platform, submit fails with a clear error
    instead of silently creating an un-publishable approval."""
    h = await _register_owner(api, async_session_factory)
    bid = (await api.post("/api/brands", headers=h, json={"name": "Brand"})).json()["id"]
    post = (await api.post("/api/social/posts", headers=h, json={
        "brand_id": bid, "platform": "linkedin", "caption": "Hi",
    })).json()

    resp = await api.post(f"/api/social/posts/{post['id']}/submit", headers=h)
    assert resp.status_code == 400
    assert resp.json()["error"]["code"] == "no_connection"

    # No approval was created.
    approvals = (await api.get("/api/approvals", headers=h)).json()
    assert not [a for a in approvals if a["action_type"] == "social_publish"]


@pytest.mark.asyncio
async def test_submit_with_explicit_connection_is_honored(api, async_session_factory):
    """When several accounts are connected for a platform, the picker's chosen
    connection_id is what the approval records (not just the first one)."""
    from app.models.approval import ApprovalRequest
    from app.models.social import SocialPost
    from app.models.social_connection import SocialConnection, SocialConnectionStatus

    h = await _register_owner(api, async_session_factory)
    me = (await api.get("/api/auth/me", headers=h)).json()
    user_id = uuid.UUID(me["id"])
    bid = (await api.post("/api/brands", headers=h, json={"name": "Brand"})).json()["id"]
    post = (await api.post("/api/social/posts", headers=h, json={
        "brand_id": bid, "platform": "facebook", "caption": "Hi",
    })).json()

    async with async_session_factory() as s:
        sp = await s.get(SocialPost, uuid.UUID(post["id"]))
        account_id = sp.account_id
        made = []
        for name in ("Page A", "Page B"):
            c = SocialConnection(
                account_id=account_id, platform="facebook", external_id=f"ext-{name}",
                display_name=name, status=SocialConnectionStatus.active,
                token_ref=f"revos/{name}", connected_by=user_id,
            )
            s.add(c)
            made.append(c)
        await s.commit()
        for c in made:
            await s.refresh(c)
        chosen_id = str(made[1].id)

    r = await api.post(f"/api/social/posts/{post['id']}/submit?connection_id={chosen_id}", headers=h)
    assert r.status_code == 200, r.text

    async with async_session_factory() as s:
        appr = (await s.execute(
            select(ApprovalRequest).where(ApprovalRequest.entity_id == uuid.UUID(post["id"]))
        )).scalar_one()
        assert appr.payload["connection_id"] == chosen_id


@pytest.mark.asyncio
async def test_reject_returns_post_to_draft(api, async_session_factory):
    h = await _register_owner(api, async_session_factory)
    bid, post_id = await _seed(api, async_session_factory, h, "facebook")

    await api.post(f"/api/social/posts/{post_id}/submit", headers=h)
    approvals = (await api.get("/api/approvals", headers=h)).json()
    approval_id = [a for a in approvals if a["action_type"] == "social_publish"][0]["id"]

    rej = await api.post(f"/api/approvals/{approval_id}/reject", headers=h, json={"reason": "no"})
    assert rej.status_code == 200

    # Post is back to draft so it can be edited and resubmitted.
    posts = (await api.get(f"/api/social/posts?brand_id={bid}", headers=h)).json()
    assert posts[0]["state"] == "draft"
