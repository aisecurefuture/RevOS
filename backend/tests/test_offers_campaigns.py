"""Offer & campaign CRUD tests (Module 5)."""

from __future__ import annotations

import pytest
from app.models.user import Role


async def _login(api, email, password):
    r = await api.post("/api/auth/login", json={"email": email, "password": password})
    assert r.status_code == 200, r.text
    return {"X-CSRF-Token": r.json()["csrf_token"]}


async def _brand(api, headers, name="Catalog Brand"):
    return (await api.post("/api/brands", headers=headers, json={"name": name})).json()["id"]


@pytest.mark.asyncio
async def test_offer_crud_and_brand_filter(api, make_user):
    h = await _login(api, **await make_user("ad@test.com", "AdminPass123", Role.admin))
    bid = await _brand(api, h)

    created = await api.post("/api/offers", headers=h, json={
        "brand_id": bid, "name": "AI Security Checklist", "offer_type": "lead_magnet"})
    assert created.status_code == 201
    offer = created.json()
    assert offer["slug"] == "ai-security-checklist"
    oid = offer["id"]

    filtered = await api.get(f"/api/offers?brand_id={bid}")
    assert filtered.status_code == 200
    assert len(filtered.json()) == 1

    updated = await api.patch(f"/api/offers/{oid}", headers=h,
                              json={"status": "active", "price_cents": 0})
    assert updated.status_code == 200
    assert updated.json()["status"] == "active"

    assert (await api.delete(f"/api/offers/{oid}", headers=h)).status_code == 200
    assert (await api.get(f"/api/offers/{oid}")).status_code == 404


@pytest.mark.asyncio
async def test_offer_rejects_javascript_payment_link(api, make_user):
    h = await _login(api, **await make_user("ad2@test.com", "AdminPass123", Role.admin))
    bid = await _brand(api, h)
    r = await api.post("/api/offers", headers=h, json={
        "brand_id": bid, "name": "Bad", "stripe_payment_link": "javascript:alert(1)"})
    assert r.status_code == 422


@pytest.mark.asyncio
async def test_offer_slug_unique_per_brand(api, make_user):
    h = await _login(api, **await make_user("ad3@test.com", "AdminPass123", Role.admin))
    bid = await _brand(api, h)
    s1 = (await api.post("/api/offers", headers=h,
                         json={"brand_id": bid, "name": "Guide"})).json()["slug"]
    s2 = (await api.post("/api/offers", headers=h,
                         json={"brand_id": bid, "name": "Guide"})).json()["slug"]
    assert s1 == "guide" and s2 == "guide-2"


@pytest.mark.asyncio
async def test_campaign_crud(api, make_user):
    h = await _login(api, **await make_user("ad4@test.com", "AdminPass123", Role.admin))
    bid = await _brand(api, h)

    created = await api.post("/api/campaigns", headers=h, json={
        "brand_id": bid, "name": "Book Launch", "channel": "email"})
    assert created.status_code == 201
    cid = created.json()["id"]
    assert created.json()["slug"] == "book-launch"

    assert (await api.get(f"/api/campaigns?brand_id={bid}")).json()[0]["id"] == cid

    updated = await api.patch(f"/api/campaigns/{cid}", headers=h, json={"status": "active"})
    assert updated.status_code == 200
    assert updated.json()["status"] == "active"

    assert (await api.delete(f"/api/campaigns/{cid}", headers=h)).status_code == 200
    assert (await api.get(f"/api/campaigns/{cid}")).status_code == 404


@pytest.mark.asyncio
async def test_editor_can_manage_offers(api, make_user):
    # Brand requires admin; create it as admin, then an editor manages offers.
    admin_h = await _login(api, **await make_user("ad5@test.com", "AdminPass123", Role.admin))
    bid = await _brand(api, admin_h)
    editor_h = await _login(api, **await make_user("ed5@test.com", "EditorPass123", Role.editor))
    r = await api.post("/api/offers", headers=editor_h,
                       json={"brand_id": bid, "name": "Editor Offer"})
    assert r.status_code == 201
