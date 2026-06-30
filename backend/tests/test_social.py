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
