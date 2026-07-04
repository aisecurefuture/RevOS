"""Scheduled social post publishing (P3-M7).

Approving a post whose scheduled_at is in the future parks it as `scheduled`
instead of publishing immediately. A beat-driven sweep (publish_scheduled_due)
publishes it once the time arrives, reusing the same platform dispatch as
immediate publish.
"""

from __future__ import annotations

import uuid
from datetime import timedelta
from unittest.mock import AsyncMock, patch

import pytest

from app.models.base import utcnow


async def _register_owner(api):
    r = await api.post("/api/auth/register", json={
        "email": "owner@test.com", "password": "OwnerPass123", "full_name": "Owner",
    })
    assert r.status_code == 201, r.text
    return {"X-CSRF-Token": r.json()["csrf_token"]}


async def _seed(api, async_session_factory, headers, scheduled_at=None):
    from app.models.social import SocialPost
    from app.models.social_connection import SocialConnection, SocialConnectionStatus

    me = (await api.get("/api/auth/me", headers=headers)).json()
    user_id = uuid.UUID(me["id"])
    bid = (await api.post("/api/brands", headers=headers, json={"name": "Brand"})).json()["id"]
    body = {"brand_id": bid, "platform": "facebook", "caption": "Hello from RevOS"}
    if scheduled_at is not None:
        body["scheduled_at"] = scheduled_at.isoformat()
    post = (await api.post("/api/social/posts", headers=headers, json=body)).json()

    async with async_session_factory() as s:
        sp = await s.get(SocialPost, uuid.UUID(post["id"]))
        account_id = sp.account_id
        conn = SocialConnection(
            account_id=account_id, platform="facebook", external_id="ext-1",
            handle="acct", display_name="Acct", status=SocialConnectionStatus.active,
            token_ref=f"revos/accounts/{account_id}/social/facebook/x",
            connected_by=user_id,
        )
        s.add(conn)
        await s.commit()
    return bid, post["id"]


@pytest.mark.asyncio
async def test_approve_with_future_schedule_parks_as_scheduled(api, async_session_factory):
    h = await _register_owner(api)
    future = utcnow() + timedelta(hours=2)
    bid, post_id = await _seed(api, async_session_factory, h, scheduled_at=future)

    submit = await api.post(f"/api/social/posts/{post_id}/submit", headers=h)
    assert submit.status_code == 200, submit.text
    approval_id = submit.json()["approval_request_id"]

    approve = await api.post(f"/api/approvals/{approval_id}/approve", headers=h)
    assert approve.status_code == 200, approve.text

    posts = (await api.get(f"/api/social/posts?brand_id={bid}", headers=h)).json()
    assert posts[0]["state"] == "scheduled"
    assert posts[0]["external_post_id"] is None  # not published yet


@pytest.mark.asyncio
async def test_approve_without_schedule_publishes_immediately(api, async_session_factory):
    """No scheduled_at (or one in the past) → publish now, same as before this feature."""
    from app.services.social import meta as meta_client

    h = await _register_owner(api)
    bid, post_id = await _seed(api, async_session_factory, h, scheduled_at=None)

    submit = await api.post(f"/api/social/posts/{post_id}/submit", headers=h)
    approval_id = submit.json()["approval_request_id"]

    with (
        patch("app.services.social_connection_service.secrets_service.get_secret",
              AsyncMock(return_value={"access_token": "tok", "page_id": "pg-1"})),
        patch.object(meta_client, "publish_to_page",
                     AsyncMock(return_value=meta_client.PublishResult(external_id="pg-1_1"))),
    ):
        approve = await api.post(f"/api/approvals/{approval_id}/approve", headers=h)
        assert approve.status_code == 200, approve.text

    posts = (await api.get(f"/api/social/posts?brand_id={bid}", headers=h)).json()
    assert posts[0]["state"] == "published"
    assert posts[0]["external_post_id"] == "pg-1_1"


@pytest.mark.asyncio
async def test_sweep_publishes_scheduled_post_once_due(api, async_session_factory):
    from app.models.content import ContentState
    from app.models.social import SocialPost
    from app.services import social_connection_service
    from app.services.social import meta as meta_client

    h = await _register_owner(api)
    # Schedule 2 hours out, approve now (parks as scheduled)...
    future = utcnow() + timedelta(hours=2)
    bid, post_id = await _seed(api, async_session_factory, h, scheduled_at=future)
    submit = await api.post(f"/api/social/posts/{post_id}/submit", headers=h)
    approval_id = submit.json()["approval_request_id"]
    await api.post(f"/api/approvals/{approval_id}/approve", headers=h)

    # ...then simulate time passing by moving scheduled_at into the past.
    async with async_session_factory() as s:
        sp = await s.get(SocialPost, uuid.UUID(post_id))
        sp.scheduled_at = utcnow() - timedelta(minutes=1)
        s.add(sp)
        await s.commit()

    with (
        patch("app.services.social_connection_service.secrets_service.get_secret",
              AsyncMock(return_value={"access_token": "tok", "page_id": "pg-1"})),
        patch.object(meta_client, "publish_to_page",
                     AsyncMock(return_value=meta_client.PublishResult(external_id="pg-1_2"))),
    ):
        async with async_session_factory() as s:
            stats = await social_connection_service.publish_scheduled_due(s)
            await s.commit()

    assert stats["published"] == 1
    posts = (await api.get(f"/api/social/posts?brand_id={bid}", headers=h)).json()
    assert posts[0]["state"] == "published"
    assert posts[0]["external_post_id"] == "pg-1_2"


@pytest.mark.asyncio
async def test_sweep_ignores_not_yet_due_posts(api, async_session_factory):
    from app.services import social_connection_service

    h = await _register_owner(api)
    future = utcnow() + timedelta(hours=2)
    bid, post_id = await _seed(api, async_session_factory, h, scheduled_at=future)
    submit = await api.post(f"/api/social/posts/{post_id}/submit", headers=h)
    approval_id = submit.json()["approval_request_id"]
    await api.post(f"/api/approvals/{approval_id}/approve", headers=h)

    async with async_session_factory() as s:
        stats = await social_connection_service.publish_scheduled_due(s)
        await s.commit()

    assert stats["published"] == 0
    posts = (await api.get(f"/api/social/posts?brand_id={bid}", headers=h)).json()
    assert posts[0]["state"] == "scheduled"
