"""Phase 2 M1 — tenant isolation.

These tests are the security contract: account A must never read, list, mutate,
or write into account B's data. They exercise the real HTTP surface (login →
scoped queries), not the internals. Each account uses its own client (its own
cookie jar) but the same underlying database.
"""

from __future__ import annotations

import contextlib

import pytest
from app.models.user import Role
from httpx import ASGITransport, AsyncClient


async def _login(client, email, password):
    r = await client.post("/api/auth/login", json={"email": email, "password": password})
    assert r.status_code == 200, r.text
    return {"X-CSRF-Token": r.json()["csrf_token"]}


async def _brand(client, h, name):
    r = await client.post("/api/brands", headers=h, json={"name": name})
    assert r.status_code == 201, r.text
    return r.json()["id"]


@contextlib.asynccontextmanager
async def _second_client(app):
    """A second API client with an independent cookie jar (same app + DB)."""
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://testserver"
    ) as client:
        yield client


@pytest.mark.asyncio
async def test_signup_creates_personal_account(api, make_user):
    """Every user gets exactly one account and can create a brand in it."""
    h = await _login(api, **await make_user("solo@test.com", "PassWord1234", Role.owner))
    bid = await _brand(api, h, "Solo Brand")
    listed = (await api.get("/api/brands", headers=h)).json()
    assert [b["id"] for b in listed] == [bid]


@pytest.mark.asyncio
async def test_brands_isolated_between_accounts(api, app, make_user):
    ha = await _login(api, **await make_user("a@test.com", "PassWord1234", Role.owner))
    a_brand = await _brand(api, ha, "A Brand")

    async with _second_client(app) as api_b:
        hb = await _login(api_b, **await make_user("b@test.com", "PassWord1234", Role.owner))
        b_brand = await _brand(api_b, hb, "B Brand")

        ids_a = {b["id"] for b in (await api.get("/api/brands", headers=ha)).json()}
        ids_b = {b["id"] for b in (await api_b.get("/api/brands", headers=hb)).json()}
        assert a_brand in ids_a and b_brand not in ids_a
        assert b_brand in ids_b and a_brand not in ids_b

        # A cannot read / patch / delete B's brand — all 404 (don't even confirm
        # existence to the other tenant).
        assert (await api.get(f"/api/brands/{b_brand}", headers=ha)).status_code == 404
        assert (
            await api.patch(f"/api/brands/{b_brand}", headers=ha, json={"name": "x"})
        ).status_code == 404
        assert (await api.delete(f"/api/brands/{b_brand}", headers=ha)).status_code == 404


@pytest.mark.asyncio
async def test_child_records_isolated_and_writes_cannot_cross(api, app, make_user):
    ha = await _login(api, **await make_user("a@test.com", "PassWord1234", Role.owner))
    a_brand = await _brand(api, ha, "A Brand")

    rc = await api.post(
        "/api/contacts", headers=ha,
        json={"brand_id": a_brand, "first_name": "Alice", "email": "alice@x.com"},
    )
    assert rc.status_code == 201, rc.text
    contact_id = rc.json()["id"]

    async with _second_client(app) as api_b:
        hb = await _login(api_b, **await make_user("b@test.com", "PassWord1234", Role.owner))

        # B cannot read A's contact by id.
        assert (await api_b.get(f"/api/contacts/{contact_id}", headers=hb)).status_code == 404

        # B listing with A's brand_id must not surface A's contact.
        lb = await api_b.get(f"/api/contacts?brand_id={a_brand}", headers=hb)
        if lb.status_code == 200:
            assert all(c["id"] != contact_id for c in lb.json())

        # B writing under A's brand_id must not land in A's account — the
        # write-stamp puts the row in B's account, so A never sees it.
        rx = await api_b.post(
            "/api/contacts", headers=hb,
            json={"brand_id": a_brand, "first_name": "Mallory"},
        )
        if rx.status_code == 201:
            injected = rx.json()["id"]
            mine = (await api.get(f"/api/contacts?brand_id={a_brand}", headers=ha)).json()
            assert all(c["id"] != injected for c in mine), "cross-tenant write leaked!"


@pytest.mark.asyncio
async def test_brandless_contacts_stay_visible_to_their_account(api, make_user):
    """Regression guard: a contact with NO brand_id (like LinkedIn imports) must
    remain visible to its own account — the denormalized account_id ensures it."""
    h = await _login(api, **await make_user("imp@test.com", "PassWord1234", Role.owner))
    rc = await api.post("/api/contacts", headers=h, json={"first_name": "NoBrand"})
    assert rc.status_code == 201, rc.text
    cid = rc.json()["id"]
    listed = (await api.get("/api/contacts", headers=h)).json()
    assert any(c["id"] == cid for c in listed), "brand-less contact vanished under scoping"
