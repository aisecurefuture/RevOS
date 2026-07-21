"""Marketplace MK3 — API wiring for cross-tenant discovery + collaboration.

Two separate accounts (each test user gets a personal workspace) exercise the
cross-tenant flow over HTTP end to end.
"""

from __future__ import annotations

import re

import pytest
from app.models.user import Role


async def _login(client, email, password):
    r = await client.post("/api/auth/login", json={"email": email, "password": password})
    assert r.status_code == 200, r.text
    return {"X-CSRF-Token": r.json()["csrf_token"]}


@pytest.mark.asyncio
async def test_full_discovery_and_collaboration_flow(make_client, make_user):
    brand_creds = await make_user("brand@test.com", "BrandPass123", Role.admin)
    creator_creds = await make_user("creator@test.com", "CreatorPass123", Role.admin)

    brand = await make_client()
    creator = await make_client()
    bh = await _login(brand, **brand_creds)
    ch = await _login(creator, **creator_creds)

    # Creator opts into the marketplace; brand publishes a discoverable product.
    cid = (await creator.post("/api/matching/creators", headers=ch, json={
        "display_name": "Ava Realtor", "handle": "@ava", "industry": "real_estate_agent",
        "follower_count": 40000, "engagement_rate": 0.05, "discoverable": True,
    })).json()["id"]
    pid = (await brand.post("/api/matching/products", headers=bh, json={
        "name": "Home Staging Co", "industry": "real_estate_agent", "status": "active",
        "discoverable": True,
    })).json()["id"]

    # Brand discovers the creator cross-tenant, ranked against its product.
    disc = await brand.get(f"/api/matching/discover/creators?rank_product_id={pid}", headers=bh)
    assert disc.status_code == 200, disc.text
    found = [r for r in disc.json() if r["creator"]["id"] == cid]
    assert found and found[0]["score"] is not None      # ranked, and no contact leaked
    assert "email" not in found[0]["creator"]

    # Brand sends a request; creator sees it incoming and accepts.
    req = await brand.post("/api/matching/collaborations", headers=bh, json={
        "direction": "brand_to_creator", "creator_id": cid, "product_id": pid,
        "message": "Love your work — collab?"})
    assert req.status_code == 201, req.text
    rid = req.json()["id"]
    assert req.json()["status"] == "pending"

    inbox = await creator.get("/api/matching/collaborations?box=incoming", headers=ch)
    assert any(x["id"] == rid for x in inbox.json())

    done = await creator.post(f"/api/matching/collaborations/{rid}/respond", headers=ch,
                              json={"accept": True, "note": "yes!"})
    assert done.status_code == 200 and done.json()["status"] == "accepted"


@pytest.mark.asyncio
async def test_only_recipient_can_respond(make_client, make_user):
    brand_creds = await make_user("b2@test.com", "BrandPass123", Role.admin)
    creator_creds = await make_user("c2@test.com", "CreatorPass123", Role.admin)
    brand, creator = await make_client(), await make_client()
    bh, ch = await _login(brand, **brand_creds), await _login(creator, **creator_creds)

    cid = (await creator.post("/api/matching/creators", headers=ch, json={
        "display_name": "C", "handle": "@c2", "discoverable": True})).json()["id"]
    pid = (await brand.post("/api/matching/products", headers=bh, json={
        "name": "P", "status": "active", "discoverable": True})).json()["id"]
    rid = (await brand.post("/api/matching/collaborations", headers=bh, json={
        "direction": "brand_to_creator", "creator_id": cid, "product_id": pid,
        "message": "hi"})).json()["id"]

    # The brand (initiator, not recipient) cannot accept its own request.
    bad = await brand.post(f"/api/matching/collaborations/{rid}/respond", headers=bh,
                           json={"accept": True})
    assert bad.status_code == 403
    assert bad.json()["error"]["code"] == "forbidden"


@pytest.mark.asyncio
async def test_non_discoverable_creator_hidden_from_discovery(make_client, make_user):
    brand_creds = await make_user("b3@test.com", "BrandPass123", Role.admin)
    creator_creds = await make_user("c3@test.com", "CreatorPass123", Role.admin)
    brand, creator = await make_client(), await make_client()
    bh, ch = await _login(brand, **brand_creds), await _login(creator, **creator_creds)

    await creator.post("/api/matching/creators", headers=ch, json={
        "display_name": "Hidden", "handle": "@hidden", "discoverable": False})
    disc = await brand.get("/api/matching/discover/creators", headers=bh)
    assert all(r["creator"]["handle"] != "@hidden" for r in disc.json())


@pytest.mark.asyncio
async def test_public_token_response(make_client, make_user, async_session_factory):
    from app.services import collaboration_service

    brand_creds = await make_user("b4@test.com", "BrandPass123", Role.admin)
    creator_creds = await make_user("c4@test.com", "CreatorPass123", Role.admin)
    brand, creator = await make_client(), await make_client()
    bh, ch = await _login(brand, **brand_creds), await _login(creator, **creator_creds)

    cid = (await creator.post("/api/matching/creators", headers=ch, json={
        "display_name": "Tok", "handle": "@tok", "discoverable": True})).json()["id"]
    pid = (await brand.post("/api/matching/products", headers=bh, json={
        "name": "P", "status": "active", "discoverable": True})).json()["id"]
    rid = (await brand.post("/api/matching/collaborations", headers=bh, json={
        "direction": "brand_to_creator", "creator_id": cid, "product_id": pid,
        "message": "hi"})).json()["id"]

    import uuid as _uuid
    url = collaboration_service.make_respond_url(_uuid.UUID(rid), accept=True)
    token = re.search(r"token=([^\"'&]+)", url).group(1)
    resp = await brand.get(f"/api/public/collab/respond?token={token}")
    assert resp.status_code == 200 and "accepted" in resp.text.lower()

    got = await creator.get(f"/api/matching/collaborations/{rid}", headers=ch)
    assert got.json()["status"] == "accepted"


@pytest.mark.asyncio
async def test_broker_requires_platform_admin(make_client, make_user):
    creds = await make_user("nb@test.com", "BrandPass123", Role.admin)
    c = await make_client()
    h = await _login(c, **creds)
    r = await c.post("/api/matching/broker/collaborations", headers=h, json={
        "initiator_account_id": "00000000-0000-0000-0000-000000000000",
        "direction": "brand_to_creator",
        "creator_id": "00000000-0000-0000-0000-000000000000", "message": "x"})
    assert r.status_code == 403
