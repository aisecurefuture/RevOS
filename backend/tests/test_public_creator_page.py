"""Public creator page + QR sharing (Phase 6) — a SEPARATE opt-in from
discoverable, a server-enforced field allow-list, and view counting."""

from __future__ import annotations

import uuid

import pytest
from app.models.user import Role


async def _login(client, email, password):
    r = await client.post("/api/auth/login", json={"email": email, "password": password})
    return {"X-CSRF-Token": r.json()["csrf_token"]}


@pytest.mark.asyncio
async def test_public_page_disabled_by_default(make_client, make_user):
    creds = await make_user("pub1@test.com", "PubPass12345", Role.admin)
    client = await make_client()
    h = await _login(client, **creds)
    cid = (await client.post("/api/matching/creators", headers=h, json={
        "display_name": "Ava", "bio": "Real estate creator"})).json()["id"]

    settings_resp = await client.get(f"/api/matching/creators/{cid}/public-page", headers=h)
    assert settings_resp.status_code == 200
    assert settings_resp.json()["enabled"] is False
    assert settings_resp.json()["slug"] is None


@pytest.mark.asyncio
async def test_enabling_generates_a_slug_and_public_page_becomes_visible(make_client, make_user):
    creds = await make_user("pub2@test.com", "PubPass12345", Role.admin)
    client = await make_client()
    h = await _login(client, **creds)
    cid = (await client.post("/api/matching/creators", headers=h, json={
        "display_name": "Ava Realtor", "bio": "Real estate creator", "industry": "real_estate_agent",
        "follower_count": 5000})).json()["id"]

    patched = await client.patch(f"/api/matching/creators/{cid}/public-page", headers=h, json={
        "enabled": True, "fields": ["bio", "industry", "follower_count"]})
    assert patched.status_code == 200, patched.text
    slug = patched.json()["slug"]
    assert slug and slug.startswith("ava-realtor")
    assert patched.json()["share_url"].endswith(f"/c/{slug}")

    public = await client.get(f"/api/public/creators/{slug}")
    assert public.status_code == 200, public.text
    body = public.json()
    assert body["display_name"] == "Ava Realtor"
    assert body["bio"] == "Real estate creator"
    assert body["industry"] == "real_estate_agent"
    assert body["follower_count"] == 5000
    assert body["view_count"] == 1


@pytest.mark.asyncio
async def test_only_opted_in_fields_are_exposed(make_client, make_user):
    """The core privacy guarantee: reputation/location must not leak just
    because they exist on the record — only what's in `fields`."""
    creds = await make_user("pub3@test.com", "PubPass12345", Role.admin)
    client = await make_client()
    h = await _login(client, **creds)
    cid = (await client.post("/api/matching/creators", headers=h, json={
        "display_name": "Private Ava", "bio": "secret bio", "location": "Austin, TX",
        "follower_count": 9999})).json()["id"]

    await client.patch(f"/api/matching/creators/{cid}/public-page", headers=h, json={
        "enabled": True, "fields": ["bio"]})   # only bio opted in
    slug = (await client.get(f"/api/matching/creators/{cid}/public-page", headers=h)).json()["slug"]

    public = await client.get(f"/api/public/creators/{slug}")
    body = public.json()
    assert body["bio"] == "secret bio"
    assert body.get("location") is None
    assert body.get("follower_count") is None


@pytest.mark.asyncio
async def test_server_rejects_a_field_outside_the_allowlist(make_client, make_user):
    creds = await make_user("pub4@test.com", "PubPass12345", Role.admin)
    client = await make_client()
    h = await _login(client, **creds)
    cid = (await client.post("/api/matching/creators", headers=h, json={
        "display_name": "Ava4"})).json()["id"]

    resp = await client.patch(f"/api/matching/creators/{cid}/public-page", headers=h, json={
        "enabled": True, "fields": ["bio", "claimed_by_user_id"]})   # not on the allow-list
    assert resp.status_code == 400
    assert resp.json()["error"]["code"] == "invalid_field"


@pytest.mark.asyncio
async def test_disabled_creator_page_is_not_publicly_reachable(make_client, make_user):
    creds = await make_user("pub5@test.com", "PubPass12345", Role.admin)
    client = await make_client()
    h = await _login(client, **creds)
    cid = (await client.post("/api/matching/creators", headers=h, json={
        "display_name": "Ava5", "bio": "hi"})).json()["id"]
    await client.patch(f"/api/matching/creators/{cid}/public-page", headers=h, json={
        "enabled": True, "fields": ["bio"]})
    slug = (await client.get(f"/api/matching/creators/{cid}/public-page", headers=h)).json()["slug"]

    # Disable it again.
    await client.patch(f"/api/matching/creators/{cid}/public-page", headers=h, json={
        "enabled": False, "fields": ["bio"]})

    resp = await client.get(f"/api/public/creators/{slug}")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_discoverable_and_public_page_are_independent(make_client, make_user):
    """A creator can be internally discoverable but NOT publicly listed, or
    vice versa — the two flags must not imply each other."""
    creds = await make_user("pub6@test.com", "PubPass12345", Role.admin)
    client = await make_client()
    h = await _login(client, **creds)
    cid = (await client.post("/api/matching/creators", headers=h, json={
        "display_name": "Ava6", "discoverable": True})).json()["id"]

    # discoverable=True but public page never enabled → no slug, no public reachability.
    settings_resp = (await client.get(f"/api/matching/creators/{cid}/public-page", headers=h)).json()
    assert settings_resp["enabled"] is False and settings_resp["slug"] is None


@pytest.mark.asyncio
async def test_slug_collision_is_rejected_with_a_friendly_error(make_client, make_user):
    creds1 = await make_user("pub7a@test.com", "PubPass12345", Role.admin)
    creds2 = await make_user("pub7b@test.com", "PubPass12345", Role.admin)
    c1, c2 = await make_client(), await make_client()
    h1, h2 = await _login(c1, **creds1), await _login(c2, **creds2)

    cid1 = (await c1.post("/api/matching/creators", headers=h1, json={"display_name": "Same Name"})).json()["id"]
    cid2 = (await c2.post("/api/matching/creators", headers=h2, json={"display_name": "Someone Else"})).json()["id"]
    await c1.patch(f"/api/matching/creators/{cid1}/public-page", headers=h1,
                   json={"enabled": True, "slug": "taken-slug", "fields": []})

    conflict = await c2.patch(f"/api/matching/creators/{cid2}/public-page", headers=h2,
                              json={"enabled": True, "slug": "taken-slug", "fields": []})
    assert conflict.status_code == 409
    assert conflict.json()["error"]["code"] == "slug_taken"


@pytest.mark.asyncio
async def test_view_count_increments_on_each_public_load(make_client, make_user):
    creds = await make_user("pub8@test.com", "PubPass12345", Role.admin)
    client = await make_client()
    h = await _login(client, **creds)
    cid = (await client.post("/api/matching/creators", headers=h, json={
        "display_name": "Ava8"})).json()["id"]
    await client.patch(f"/api/matching/creators/{cid}/public-page", headers=h,
                       json={"enabled": True, "fields": []})
    slug = (await client.get(f"/api/matching/creators/{cid}/public-page", headers=h)).json()["slug"]

    for _ in range(3):
        await client.get(f"/api/public/creators/{slug}")
    final = await client.get(f"/api/public/creators/{slug}")
    assert final.json()["view_count"] == 4


@pytest.mark.asyncio
async def test_reputation_field_includes_tier_when_opted_in(make_client, make_user):
    creds = await make_user("pub9@test.com", "PubPass12345", Role.admin)
    client = await make_client()
    h = await _login(client, **creds)
    cid = (await client.post("/api/matching/creators", headers=h, json={
        "display_name": "Ava9"})).json()["id"]
    await client.patch(f"/api/matching/creators/{cid}/public-page", headers=h,
                       json={"enabled": True, "fields": ["reputation"]})
    slug = (await client.get(f"/api/matching/creators/{cid}/public-page", headers=h)).json()["slug"]

    public = await client.get(f"/api/public/creators/{slug}")
    body = public.json()
    assert "reputation" in body and body["reputation"] is not None
    assert body["reputation"]["tier"] in {"Top-Rated", "Trusted", "Growing", "New"}


@pytest.mark.asyncio
async def test_stranger_cannot_read_or_edit_someone_elses_public_settings(make_client, make_user):
    owner_creds = await make_user("pub10a@test.com", "PubPass12345", Role.admin)
    stranger_creds = await make_user("pub10b@test.com", "PubPass12345", Role.admin)
    owner, stranger = await make_client(), await make_client()
    oh, xh = await _login(owner, **owner_creds), await _login(stranger, **stranger_creds)
    cid = (await owner.post("/api/matching/creators", headers=oh, json={
        "display_name": "Ava10"})).json()["id"]

    denied_get = await stranger.get(f"/api/matching/creators/{cid}/public-page", headers=xh)
    assert denied_get.status_code == 404
    denied_patch = await stranger.patch(f"/api/matching/creators/{cid}/public-page", headers=xh,
                                        json={"enabled": True, "fields": []})
    assert denied_patch.status_code == 404
