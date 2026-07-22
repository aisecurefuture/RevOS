"""Reputation RK3 — feedback workflow: submit review, respond, list, prompts.

Two separate tenants (brand + creator) drive a real accepted collaboration
over HTTP, then exercise the review flow on top of it.
"""

from __future__ import annotations

import pytest
from app.models.user import Role


async def _login(client, email, password):
    r = await client.post("/api/auth/login", json={"email": email, "password": password})
    assert r.status_code == 200, r.text
    return {"X-CSRF-Token": r.json()["csrf_token"]}


async def _accepted_collaboration(make_client, make_user, *, brand_email, creator_email):
    """Full setup: two tenants, a discoverable creator + product, a
    brand_to_creator request, accepted. Returns (brand, bh, creator, ch, cid, pid, rid)."""
    brand_creds = await make_user(brand_email, "BrandPass123", Role.admin)
    creator_creds = await make_user(creator_email, "CreatorPass123", Role.admin)
    brand, creator = await make_client(), await make_client()
    bh, ch = await _login(brand, **brand_creds), await _login(creator, **creator_creds)

    cid = (await creator.post("/api/matching/creators", headers=ch, json={
        "display_name": "Ava", "handle": f"@{creator_email}", "discoverable": True})).json()["id"]
    pid = (await brand.post("/api/matching/products", headers=bh, json={
        "name": "Staging Co", "status": "active", "discoverable": True})).json()["id"]
    rid = (await brand.post("/api/matching/collaborations", headers=bh, json={
        "direction": "brand_to_creator", "creator_id": cid, "product_id": pid,
        "message": "collab?"})).json()["id"]
    accepted = await creator.post(f"/api/matching/collaborations/{rid}/respond", headers=ch,
                                  json={"accept": True})
    assert accepted.status_code == 200 and accepted.json()["status"] == "accepted"
    return brand, bh, creator, ch, cid, pid, rid


@pytest.mark.asyncio
async def test_brand_reviews_creator_and_creator_reviews_brand(make_client, make_user):
    brand, bh, creator, ch, cid, pid, rid = await _accepted_collaboration(
        make_client, make_user, brand_email="b1@test.com", creator_email="c1@test.com")

    # Brand reviews the creator.
    r1 = await brand.post(f"/api/matching/collaborations/{rid}/reviews", headers=bh, json={
        "collaboration_request_id": rid, "rating": 5,
        "dimension_ratings": {"communication": 5}, "comment": "Great collab!"})
    assert r1.status_code == 201, r1.text
    assert r1.json()["direction"] == "brand_reviews_creator"
    assert r1.json()["subject_creator_id"] == cid

    # Creator reviews the brand/product.
    r2 = await creator.post(f"/api/matching/collaborations/{rid}/reviews", headers=ch, json={
        "collaboration_request_id": rid, "rating": 4, "comment": "Paid on time."})
    assert r2.status_code == 201, r2.text
    assert r2.json()["direction"] == "creator_reviews_brand"
    assert r2.json()["subject_product_id"] == pid

    # Both visible on the collaboration.
    listed = await brand.get(f"/api/matching/collaborations/{rid}/reviews", headers=bh)
    assert len(listed.json()) == 2

    # And on the public subject listings.
    creator_reviews = await brand.get(f"/api/matching/creators/{cid}/reviews", headers=bh)
    assert len(creator_reviews.json()) == 1 and creator_reviews.json()[0]["rating"] == 5
    product_reviews = await creator.get(f"/api/matching/products/{pid}/reviews", headers=ch)
    assert len(product_reviews.json()) == 1 and product_reviews.json()[0]["rating"] == 4


@pytest.mark.asyncio
async def test_cannot_review_twice(make_client, make_user):
    brand, bh, creator, ch, cid, pid, rid = await _accepted_collaboration(
        make_client, make_user, brand_email="b2@test.com", creator_email="c2@test.com")
    ok = await brand.post(f"/api/matching/collaborations/{rid}/reviews", headers=bh,
                          json={"collaboration_request_id": rid, "rating": 5})
    assert ok.status_code == 201
    dupe = await brand.post(f"/api/matching/collaborations/{rid}/reviews", headers=bh,
                            json={"collaboration_request_id": rid, "rating": 1})
    assert dupe.status_code == 409
    assert dupe.json()["error"]["code"] == "already_reviewed"


@pytest.mark.asyncio
async def test_non_party_cannot_review(make_client, make_user):
    brand, bh, creator, ch, cid, pid, rid = await _accepted_collaboration(
        make_client, make_user, brand_email="b3@test.com", creator_email="c3@test.com")
    outsider_creds = await make_user("outsider@test.com", "OutsiderPass123", Role.admin)
    outsider = await make_client()
    oh = await _login(outsider, **outsider_creds)
    resp = await outsider.post(f"/api/matching/collaborations/{rid}/reviews", headers=oh,
                               json={"collaboration_request_id": rid, "rating": 5})
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_cannot_review_a_pending_or_declined_collaboration(make_client, make_user):
    brand_creds = await make_user("b4@test.com", "BrandPass123", Role.admin)
    creator_creds = await make_user("c4@test.com", "CreatorPass123", Role.admin)
    brand, creator = await make_client(), await make_client()
    bh, ch = await _login(brand, **brand_creds), await _login(creator, **creator_creds)

    cid = (await creator.post("/api/matching/creators", headers=ch, json={
        "display_name": "Ava", "handle": "@ava4", "discoverable": True})).json()["id"]
    pid = (await brand.post("/api/matching/products", headers=bh, json={
        "name": "Staging Co", "status": "active", "discoverable": True})).json()["id"]
    rid = (await brand.post("/api/matching/collaborations", headers=bh, json={
        "direction": "brand_to_creator", "creator_id": cid, "product_id": pid,
        "message": "collab?"})).json()["id"]

    # Still pending — not reviewable.
    resp = await brand.post(f"/api/matching/collaborations/{rid}/reviews", headers=bh,
                            json={"collaboration_request_id": rid, "rating": 5})
    assert resp.status_code == 409
    assert resp.json()["error"]["code"] == "not_reviewable"

    # Declined — still not reviewable.
    await creator.post(f"/api/matching/collaborations/{rid}/respond", headers=ch,
                       json={"accept": False})
    resp2 = await brand.post(f"/api/matching/collaborations/{rid}/reviews", headers=bh,
                             json={"collaboration_request_id": rid, "rating": 5})
    assert resp2.status_code == 409


@pytest.mark.asyncio
async def test_only_subject_can_respond_to_review(make_client, make_user):
    brand, bh, creator, ch, cid, pid, rid = await _accepted_collaboration(
        make_client, make_user, brand_email="b5@test.com", creator_email="c5@test.com")
    review_id = (await brand.post(f"/api/matching/collaborations/{rid}/reviews", headers=bh,
                                  json={"collaboration_request_id": rid, "rating": 2,
                                       "comment": "Slow replies."})).json()["id"]

    # The reviewer (brand) cannot respond to their own review.
    bad = await brand.post(f"/api/matching/reviews/{review_id}/respond", headers=bh,
                           json={"response": "self-defense"})
    assert bad.status_code == 403

    # The subject (creator) can.
    good = await creator.post(f"/api/matching/reviews/{review_id}/respond", headers=ch,
                              json={"response": "Had a family emergency that week."})
    assert good.status_code == 200
    assert good.json()["response"] == "Had a family emergency that week."

    # Can't respond twice.
    again = await creator.post(f"/api/matching/reviews/{review_id}/respond", headers=ch,
                               json={"response": "again"})
    assert again.status_code == 409


@pytest.mark.asyncio
async def test_pending_review_prompts_clears_after_reviewing(make_client, make_user):
    brand, bh, creator, ch, cid, pid, rid = await _accepted_collaboration(
        make_client, make_user, brand_email="b6@test.com", creator_email="c6@test.com")

    before = await brand.get("/api/matching/collaborations/pending-reviews", headers=bh)
    assert any(x["id"] == rid for x in before.json())

    await brand.post(f"/api/matching/collaborations/{rid}/reviews", headers=bh,
                     json={"collaboration_request_id": rid, "rating": 5})

    after = await brand.get("/api/matching/collaborations/pending-reviews", headers=bh)
    assert all(x["id"] != rid for x in after.json())


@pytest.mark.asyncio
async def test_review_feeds_reputation_score(make_client, make_user):
    brand, bh, creator, ch, cid, pid, rid = await _accepted_collaboration(
        make_client, make_user, brand_email="b7@test.com", creator_email="c7@test.com")
    await brand.post(f"/api/matching/collaborations/{rid}/reviews", headers=bh,
                     json={"collaboration_request_id": rid, "rating": 5})

    rep = await brand.get(f"/api/matching/creators/{cid}/reputation", headers=bh)
    assert rep.status_code == 200
    assert rep.json()["review_count"] == 1
    review_dim = next(d for d in rep.json()["dimensions"] if d["key"] == "review_reputation")
    assert review_dim["available"] is True
