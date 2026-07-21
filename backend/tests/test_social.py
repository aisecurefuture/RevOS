"""Social adapters, posts, draft publishing, and the Hao seed (Module 10)."""

from __future__ import annotations

import pytest
from app.models.social import SocialPost
from app.models.user import Role
from sqlmodel import select


async def _login(api, email, password):
    r = await api.post("/api/auth/login", json={"email": email, "password": password})
    assert r.status_code == 200, r.text
    return {"X-CSRF-Token": r.json()["csrf_token"]}


@pytest.mark.asyncio
async def test_adapters_unconfigured_by_default(api, make_user):
    await _login(api, **await make_user("admin@test.com", "AdminPass123", Role.admin))
    status = await api.get("/api/social/status")
    assert status.status_code == 200
    # With no API keys, every platform is draft/copy-paste only.
    assert all(v is False for v in status.json()["adapters"].values())


@pytest.mark.asyncio
async def test_social_post_publish_is_draft_without_keys(api, make_user):
    h = await _login(api, **await make_user("admin@test.com", "AdminPass123", Role.admin))
    bid = (await api.post("/api/brands", headers=h, json={"name": "Social Brand"})).json()["id"]
    campaign = (await api.post("/api/social/campaigns", headers=h, json={
        "brand_id": bid, "name": "Launch", "platforms": ["instagram"]})).json()
    post = (await api.post("/api/social/posts", headers=h, json={
        "brand_id": bid, "platform": "instagram", "social_campaign_id": campaign["id"],
        "caption": "Hello world", "hashtags": ["launch"]})).json()

    result = await api.post(f"/api/social/posts/{post['id']}/publish", headers=h)
    assert result.status_code == 200
    body = result.json()
    # Not auto-posted — returned as a copy-paste-ready draft.
    assert body["published"] is False
    assert body["mode"] == "draft"


@pytest.mark.asyncio
async def test_publish_requires_admin(api, make_user):
    admin_h = await _login(api, **await make_user("admin@test.com", "AdminPass123", Role.admin))
    bid = (await api.post("/api/brands", headers=admin_h, json={"name": "B"})).json()["id"]
    post = (await api.post("/api/social/posts", headers=admin_h, json={
        "brand_id": bid, "platform": "tiktok", "caption": "x"})).json()
    editor_h = await _login(api, **await make_user("ed@test.com", "EditorPass123", Role.editor))
    assert (await api.post(f"/api/social/posts/{post['id']}/publish",
                           headers=editor_h)).status_code == 403


@pytest.mark.asyncio
async def test_hao_campaign_seed(async_session_factory):
    from app.seed.hao_campaign import seed_hao_campaign

    async with async_session_factory() as s:
        result = await seed_hao_campaign(s)
        await s.commit()
    assert result["created"] is True
    assert result["posts"] == 5

    async with async_session_factory() as s:
        posts = (await s.execute(select(SocialPost))).scalars().all()
        assert len(posts) == 5
        assert all(p.state == "draft" for p in posts)  # nothing auto-published
        # Idempotent: a second run creates nothing.
        again = await seed_hao_campaign(s)
        assert again["created"] is False


@pytest.mark.asyncio
async def test_upload_post_media_returns_storage_key(api, make_user):
    """Attaching a photo stores it and returns a media_url usable in a post."""
    h = await _login(api, **await make_user("admin@test.com", "AdminPass123", Role.admin))
    bid = (await api.post("/api/brands", headers=h, json={"name": "Media Brand"})).json()["id"]
    files = {"file": ("shot.jpg", b"\xff\xd8\xff\xd9imagebytes", "image/jpeg")}
    r = await api.post("/api/social/upload-media", headers=h, data={"brand_id": bid}, files=files)
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["media_url"].startswith("media/")
    assert body["kind"] == "image"

    # The returned key is accepted as a post's media_urls entry.
    post = await api.post("/api/social/posts", headers=h, json={
        "brand_id": bid, "platform": "linkedin", "caption": "hi", "media_urls": [body["media_url"]],
    })
    assert post.status_code == 201, post.text
    assert post.json()["media_urls"] == [body["media_url"]]


@pytest.mark.asyncio
async def test_upload_post_media_rejects_bad_type(api, make_user):
    h = await _login(api, **await make_user("admin@test.com", "AdminPass123", Role.admin))
    bid = (await api.post("/api/brands", headers=h, json={"name": "Media Brand"})).json()["id"]
    files = {"file": ("evil.exe", b"MZ\x90\x00", "application/x-msdownload")}
    r = await api.post("/api/social/upload-media", headers=h, data={"brand_id": bid}, files=files)
    assert r.status_code == 400
    assert r.json()["error"]["code"] == "bad_media_type"


@pytest.mark.asyncio
async def test_scheduling_accepts_timezone_aware_time(api, make_user):
    """A tz-aware ISO instant (…Z from the browser) must not 500 — the naive
    UTC column would otherwise reject it (asyncpg)."""
    h = await _login(api, **await make_user("sched@test.com", "AdminPass123", Role.admin))
    bid = (await api.post("/api/brands", headers=h, json={"name": "Sched Brand"})).json()["id"]
    r = await api.post("/api/social/posts", headers=h, json={
        "brand_id": bid, "platform": "linkedin", "caption": "later",
        "scheduled_at": "2026-08-01T15:30:00Z",
    })
    assert r.status_code == 201, r.text
    # Stored/returned as naive UTC (no offset).
    assert r.json()["scheduled_at"].startswith("2026-08-01T15:30:00")
    assert "+00:00" not in r.json()["scheduled_at"]
