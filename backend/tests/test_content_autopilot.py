"""Content autopilot (Phase 3) — generate → gate → (auto-)publish.

Generation is mocked (no real LLM); the tests pin down the *routing*, which is
the safety-critical part: blocked content is discarded, flagged content is
queued for a human even in full autopilot, and only clean content auto-publishes.
"""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, patch

import pytest

from app.services import content_autopilot_service as svc


async def _register_owner(api, email="owner@test.com"):
    r = await api.post("/api/auth/register", json={
        "email": email, "password": "OwnerPass123", "full_name": "Owner",
    })
    assert r.status_code == 201, r.text
    return {"X-CSRF-Token": r.json()["csrf_token"]}


async def _setup(api, async_session_factory, headers, *, auto_publish: bool,
                 banned: list[str] | None = None):
    """Brand with a published book (one approved claim grounding 10,000), an
    active facebook connection, and an autopilot config targeting facebook."""
    from app.models.social import SocialPost
    from app.models.social_connection import SocialConnection, SocialConnectionStatus

    me = (await api.get("/api/auth/me", headers=headers)).json()
    user_id = uuid.UUID(me["id"])
    bid = (await api.post("/api/brands", headers=headers, json={"name": "Acme"})).json()["id"]

    await api.patch(f"/api/brand-book/{bid}", headers=headers, json={
        "is_published": True, **({"banned_terms": banned} if banned else {}),
    })
    await api.post(f"/api/brand-book/{bid}/claims", headers=headers, json={
        "claim": "Trusted by 10,000 teams", "category": "metric",
    })

    # Seed an active facebook connection on this account.
    async with async_session_factory() as s:
        # learn the account_id from a throwaway post
        tmp = (await api.post("/api/social/posts", headers=headers, json={
            "brand_id": bid, "platform": "facebook", "caption": "seed",
        })).json()
        sp = await s.get(SocialPost, uuid.UUID(tmp["id"]))
        account_id = sp.account_id
        # remove the throwaway so it doesn't pollute assertions
        sp.deleted_at = sp.updated_at
        s.add(SocialConnection(
            account_id=account_id, platform="facebook", external_id="ext-1",
            display_name="Page", status=SocialConnectionStatus.active,
            token_ref="revos/x", connected_by=user_id,
        ))
        s.add(sp)
        await s.commit()

    await api.patch(f"/api/autopilot/{bid}", headers=headers, json={
        "enabled": True, "auto_publish": auto_publish, "platforms": ["facebook"], "posts_per_run": 1,
    })
    return bid


async def _posts(api, headers, bid):
    posts = (await api.get(f"/api/social/posts?brand_id={bid}", headers=headers)).json()
    return [p for p in posts if p["caption"] != "seed"]


# ---------------------------------------------------------------------------
# Routing
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_clean_content_auto_publishes(api, async_session_factory):
    from app.services.social import meta as meta_client

    h = await _register_owner(api)
    bid = await _setup(api, async_session_factory, h, auto_publish=True)

    with (
        patch.object(svc, "generate_caption",
                     AsyncMock(return_value="Launch day — try it free today! 🚀 #launch")),
        patch("app.services.social_connection_service.secrets_service.get_secret",
              AsyncMock(return_value={"access_token": "tok", "page_id": "pg-1"})),
        patch.object(meta_client, "publish_to_page",
                     AsyncMock(return_value=meta_client.PublishResult(external_id="pg-1_1"))),
    ):
        run = (await api.post(f"/api/autopilot/{bid}/run", headers=h)).json()

    assert run["published"] == 1
    assert run["blocked"] == 0 and run["queued"] == 0
    posts = await _posts(api, h, bid)
    assert len(posts) == 1
    assert posts[0]["state"] == "published"
    assert posts[0]["external_post_id"] == "pg-1_1"


@pytest.mark.asyncio
async def test_blocked_content_is_discarded(api, async_session_factory):
    h = await _register_owner(api)
    bid = await _setup(api, async_session_factory, h, auto_publish=True, banned=["guarantee"])

    with patch.object(svc, "generate_caption",
                      AsyncMock(return_value="We guarantee amazing results! #results")):
        run = (await api.post(f"/api/autopilot/{bid}/run", headers=h)).json()

    assert run["generated"] == 1 and run["blocked"] == 1
    assert run["published"] == 0 and run["queued"] == 0
    assert await _posts(api, h, bid) == []  # nothing created


@pytest.mark.asyncio
async def test_flagged_content_is_queued_not_published(api, async_session_factory):
    """An ungrounded statistic must never auto-publish, even in full autopilot."""
    h = await _register_owner(api)
    bid = await _setup(api, async_session_factory, h, auto_publish=True)

    with patch.object(svc, "generate_caption",
                      AsyncMock(return_value="We now serve 999999 customers! #growth")):
        run = (await api.post(f"/api/autopilot/{bid}/run", headers=h)).json()

    assert run["published"] == 0
    assert run["queued"] == 1
    posts = await _posts(api, h, bid)
    assert len(posts) == 1
    assert posts[0]["state"] == "needs_review"  # waiting for a human


@pytest.mark.asyncio
async def test_grounded_number_passes(api, async_session_factory):
    from app.services.social import meta as meta_client

    h = await _register_owner(api)
    bid = await _setup(api, async_session_factory, h, auto_publish=True)

    with (
        patch.object(svc, "generate_caption",
                     AsyncMock(return_value="Now trusted by 10,000 teams. Join them! #trust")),
        patch("app.services.social_connection_service.secrets_service.get_secret",
              AsyncMock(return_value={"access_token": "tok", "page_id": "pg-1"})),
        patch.object(meta_client, "publish_to_page",
                     AsyncMock(return_value=meta_client.PublishResult(external_id="pg-1_2"))),
    ):
        run = (await api.post(f"/api/autopilot/{bid}/run", headers=h)).json()

    assert run["published"] == 1  # 10,000 is a grounded approved claim


@pytest.mark.asyncio
async def test_auto_publish_off_queues_clean_content(api, async_session_factory):
    h = await _register_owner(api)
    bid = await _setup(api, async_session_factory, h, auto_publish=False)

    with patch.object(svc, "generate_caption",
                      AsyncMock(return_value="Ship faster with less stress. Try it. #tools")):
        run = (await api.post(f"/api/autopilot/{bid}/run", headers=h)).json()

    assert run["published"] == 0 and run["queued"] == 1
    posts = await _posts(api, h, bid)
    assert posts[0]["state"] == "needs_review"


@pytest.mark.asyncio
async def test_unpublished_book_skips(api, async_session_factory):
    h = await _register_owner(api)
    bid = await _setup(api, async_session_factory, h, auto_publish=True)
    # Un-publish the book.
    await api.patch(f"/api/brand-book/{bid}", headers=h, json={"is_published": False})

    with patch.object(svc, "generate_caption", AsyncMock(return_value="anything")) as gen:
        run = (await api.post(f"/api/autopilot/{bid}/run", headers=h)).json()

    assert run["generated"] == 0 and run["published"] == 0
    gen.assert_not_awaited()  # never even generated


# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_config_crud_and_admin_only(api, make_user):
    from app.models.user import Role

    h = await _register_owner(api)
    bid = (await api.post("/api/brands", headers=h, json={"name": "B"})).json()["id"]

    got = await api.patch(f"/api/autopilot/{bid}", headers=h, json={
        "enabled": True, "platforms": ["facebook", "linkedin"], "posts_per_run": 3,
    })
    assert got.status_code == 200
    assert got.json()["enabled"] is True and got.json()["posts_per_run"] == 3

    async def _login(email, password):
        r = await api.post("/api/auth/login", json={"email": email, "password": password})
        return {"X-CSRF-Token": r.json()["csrf_token"]}

    ed = await _login(**await make_user("ed@test.com", "EditorPass123", Role.editor))
    assert (await api.patch(f"/api/autopilot/{bid}", headers=ed, json={"enabled": True})).status_code in (403, 404)


@pytest.mark.asyncio
async def test_media_platform_queues_not_publishes_even_with_autopublish(api, async_session_factory):
    """Instagram/YouTube/TikTok need media; autopilot must draft the caption and
    QUEUE it (for a human to attach media + approve), never auto-publish empty."""
    from app.models.social import SocialPost
    from app.models.social_connection import SocialConnection, SocialConnectionStatus

    h = await _register_owner(api)
    me = (await api.get("/api/auth/me", headers=h)).json()
    user_id = uuid.UUID(me["id"])
    bid = (await api.post("/api/brands", headers=h, json={"name": "Acme"})).json()["id"]
    await api.patch(f"/api/brand-book/{bid}", headers=h, json={"is_published": True})
    await api.post(f"/api/brand-book/{bid}/claims", headers=h, json={
        "claim": "Trusted by 10,000 teams", "category": "metric",
    })

    async with async_session_factory() as s:
        tmp = (await api.post("/api/social/posts", headers=h, json={
            "brand_id": bid, "platform": "instagram", "caption": "seed",
        })).json()
        sp = await s.get(SocialPost, uuid.UUID(tmp["id"]))
        account_id = sp.account_id
        sp.deleted_at = sp.updated_at
        s.add(SocialConnection(
            account_id=account_id, platform="instagram", external_id="ig-1",
            display_name="IG", status=SocialConnectionStatus.active,
            token_ref="revos/ig", connected_by=user_id,
        ))
        s.add(sp)
        await s.commit()

    await api.patch(f"/api/autopilot/{bid}", headers=h, json={
        "enabled": True, "auto_publish": True, "platforms": ["instagram"], "posts_per_run": 1,
    })

    with patch.object(svc, "generate_caption",
                      AsyncMock(return_value="Behind the scenes today ✨ #brand")):
        run = (await api.post(f"/api/autopilot/{bid}/run", headers=h)).json()

    # Clean caption, auto_publish on — but media platform → queued, not published.
    assert run["queued"] == 1
    assert run["published"] == 0
    posts = await _posts(api, h, bid)
    assert len(posts) == 1
    assert posts[0]["state"] != "published"
