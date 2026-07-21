"""AI Matching Engine API — creators, products, ranked matches (M3)."""

from __future__ import annotations

import pytest
from app.models.user import Role


async def _login(api, email, password):
    r = await api.post("/api/auth/login", json={"email": email, "password": password})
    assert r.status_code == 200, r.text
    return {"X-CSRF-Token": r.json()["csrf_token"]}


async def _admin(api, make_user):
    return await _login(api, **await make_user("admin@test.com", "AdminPass123", Role.admin))


def _strong_creator(**over):
    base = dict(
        display_name="Ava Realtor", handle="@ava", industry="real_estate_agent",
        topics=["real estate", "home decor"], follower_count=48_000, engagement_rate=0.055,
        demographics={
            "age": {"25-34": 0.42, "35-44": 0.30, "18-24": 0.18, "45-54": 0.10},
            "gender": {"female": 0.64, "male": 0.36},
            "locations": [{"name": "Austin, TX", "share": 0.3}, {"name": "US", "share": 0.85}],
        },
    )
    base.update(over)
    return base


def _product(**over):
    base = dict(
        name="Home Staging Co.", industry="real_estate_agent", status="active",
        description="Home-staging service for agents listing family homes.",
        target_audience={"age_min": 25, "age_max": 44, "gender_skew": "female",
                         "locations": ["Austin, TX", "US"], "interests": ["home buying", "staging"]},
    )
    base.update(over)
    return base


@pytest.mark.asyncio
async def test_create_creator_derives_size_tier_and_primary_industry(api, make_user):
    h = await _admin(api, make_user)
    r = await api.post("/api/matching/creators", headers=h, json=_strong_creator(follower_count=48_000))
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["size_tier"] == "micro"        # 10k–100k
    assert body["industry"] == "real_estate_agent"


@pytest.mark.asyncio
async def test_primary_industry_backfilled_from_affinity(api, make_user):
    h = await _admin(api, make_user)
    r = await api.post("/api/matching/creators", headers=h, json=_strong_creator(
        industry=None,
        industries=[{"industry": "real_estate_agent", "weight": 0.7},
                    {"industry": "interior_designer", "weight": 0.3}],
    ))
    assert r.status_code == 201, r.text
    assert r.json()["industry"] == "real_estate_agent"   # highest weight becomes primary


@pytest.mark.asyncio
async def test_product_matches_rank_strong_creator_first(api, make_user):
    h = await _admin(api, make_user)
    await api.post("/api/matching/creators", headers=h, json=_strong_creator())
    await api.post("/api/matching/creators", headers=h, json=_strong_creator(
        display_name="Gym Bro", handle="@gym", industry="fitness", topics=["gym", "protein"],
        engagement_rate=0.004,
        demographics={"gender": {"male": 0.9, "female": 0.1}}))
    pid = (await api.post("/api/matching/products", headers=h, json=_product())).json()["id"]

    r = await api.get(f"/api/matching/products/{pid}/matches", headers=h)
    assert r.status_code == 200, r.text
    results = r.json()
    assert len(results) == 2
    assert results[0]["creator"]["display_name"] == "Ava Realtor"
    assert results[0]["score"]["overall"] > results[1]["score"]["overall"]
    assert len(results[0]["score"]["dimensions"]) == 4
    assert "match" in results[0]["score"]["rationale"].lower()


@pytest.mark.asyncio
async def test_creator_matches_returns_ranked_products(api, make_user):
    h = await _admin(api, make_user)
    cid = (await api.post("/api/matching/creators", headers=h, json=_strong_creator())).json()["id"]
    await api.post("/api/matching/products", headers=h, json=_product(name="Aligned"))
    await api.post("/api/matching/products", headers=h, json=_product(
        name="Off-target", industry="fitness",
        target_audience={"gender_skew": "male", "interests": ["supplements"]}))

    r = await api.get(f"/api/matching/creators/{cid}/matches", headers=h)
    assert r.status_code == 200, r.text
    names = [m["product"]["name"] for m in r.json()]
    assert names[0] == "Aligned"


@pytest.mark.asyncio
async def test_update_recomputes_size_tier_and_delete(api, make_user):
    h = await _admin(api, make_user)
    cid = (await api.post("/api/matching/creators", headers=h, json=_strong_creator())).json()["id"]
    up = await api.patch(f"/api/matching/creators/{cid}", headers=h, json={"follower_count": 2_000_000})
    assert up.status_code == 200 and up.json()["size_tier"] == "mega"

    assert (await api.delete(f"/api/matching/creators/{cid}", headers=h)).status_code == 200
    listed = await api.get("/api/matching/creators", headers=h)
    assert all(c["id"] != cid for c in listed.json())


@pytest.mark.asyncio
async def test_draft_products_excluded_from_creator_matches(api, make_user):
    h = await _admin(api, make_user)
    cid = (await api.post("/api/matching/creators", headers=h, json=_strong_creator())).json()["id"]
    await api.post("/api/matching/products", headers=h, json=_product(name="Draft one", status="draft"))
    r = await api.get(f"/api/matching/creators/{cid}/matches", headers=h)
    assert all(m["product"]["name"] != "Draft one" for m in r.json())
