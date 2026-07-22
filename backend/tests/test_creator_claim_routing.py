"""Routing after claim (Phase 6 continued): a claimed creator's own account
becomes the party for NEW collaboration requests, while the agency's past
history stays untouched. The claimed creator may also initiate on their own
behalf, in addition to their managing agency."""

from __future__ import annotations

import pytest
from app.models.user import Role


async def _login(client, email, password):
    r = await client.post("/api/auth/login", json={"email": email, "password": password})
    return {"X-CSRF-Token": r.json()["csrf_token"]}


async def _agency_and_claimed_creator(make_client, make_user, *, agency_email, creator_email):
    agency_creds = await make_user(agency_email, "AgencyPass123", Role.admin)
    creator_creds = await make_user(creator_email, "CreatorPass1234", Role.admin)
    agency, creator = await make_client(), await make_client()
    ah, ch = await _login(agency, **agency_creds), await _login(creator, **creator_creds)

    cid = (await agency.post("/api/matching/creators", headers=ah, json={
        "display_name": "Ava", "discoverable": True})).json()["id"]
    invite = (await agency.post(f"/api/matching/creators/{cid}/claim-invite", headers=ah)).json()
    await creator.post("/api/matching/creators/claim", headers=ch, json={"token": invite["token"]})
    return agency, ah, creator, ch, cid


@pytest.mark.asyncio
async def test_new_request_routes_to_claimed_creators_own_account(make_client, make_user):
    agency, ah, creator, ch, cid = await _agency_and_claimed_creator(
        make_client, make_user, agency_email="rtagency1@test.com", creator_email="rtcreator1@test.com")

    brand_creds = await make_user("rtbrand1@test.com", "BrandPass123", Role.admin)
    brand = await make_client()
    bh = await _login(brand, **brand_creds)
    pid = (await brand.post("/api/matching/products", headers=bh, json={
        "name": "Staging Co", "status": "active", "discoverable": True})).json()["id"]

    rid = (await brand.post("/api/matching/collaborations", headers=bh, json={
        "direction": "brand_to_creator", "creator_id": cid, "product_id": pid,
        "message": "collab?"})).json()["id"]

    # The AGENCY no longer sees this as incoming — the CREATOR does.
    agency_inbox = await agency.get("/api/matching/collaborations?box=incoming", headers=ah)
    assert all(x["id"] != rid for x in agency_inbox.json())
    creator_inbox = await creator.get("/api/matching/collaborations?box=incoming", headers=ch)
    assert any(x["id"] == rid for x in creator_inbox.json())

    # And the creator (not the agency) can accept it, spawning their own workspace.
    accepted = await creator.post(f"/api/matching/collaborations/{rid}/respond", headers=ch,
                                  json={"accept": True})
    assert accepted.status_code == 200 and accepted.json()["status"] == "accepted"
    ws = await creator.get("/api/matching/workspaces", headers=ch)
    assert any(w["collaboration_request_id"] == rid for w in ws.json())


@pytest.mark.asyncio
async def test_claimed_creator_can_initiate_on_own_behalf(make_client, make_user):
    agency, ah, creator, ch, cid = await _agency_and_claimed_creator(
        make_client, make_user, agency_email="rtagency2@test.com", creator_email="rtcreator2@test.com")

    brand_creds = await make_user("rtbrand2@test.com", "BrandPass123", Role.admin)
    brand = await make_client()
    bh = await _login(brand, **brand_creds)
    pid = (await brand.post("/api/matching/products", headers=bh, json={
        "name": "Staging Co 2", "status": "active", "discoverable": True})).json()["id"]

    sent = await creator.post("/api/matching/collaborations", headers=ch, json={
        "direction": "creator_to_brand", "creator_id": cid, "product_id": pid,
        "message": "I'd love to work with you!"})
    assert sent.status_code == 201, sent.text


@pytest.mark.asyncio
async def test_stranger_still_cannot_initiate_for_a_claimed_creator(make_client, make_user):
    agency, ah, creator, ch, cid = await _agency_and_claimed_creator(
        make_client, make_user, agency_email="rtagency3@test.com", creator_email="rtcreator3@test.com")

    stranger_creds = await make_user("rtstranger3@test.com", "StrangerPass123", Role.admin)
    stranger = await make_client()
    xh = await _login(stranger, **stranger_creds)
    brand_creds = await make_user("rtbrand3@test.com", "BrandPass123", Role.admin)
    brand = await make_client()
    bh = await _login(brand, **brand_creds)
    pid = (await brand.post("/api/matching/products", headers=bh, json={
        "name": "Staging Co 3", "status": "active", "discoverable": True})).json()["id"]

    denied = await stranger.post("/api/matching/collaborations", headers=xh, json={
        "direction": "creator_to_brand", "creator_id": cid, "product_id": pid,
        "message": "let me pretend to be them"})
    assert denied.status_code == 403


@pytest.mark.asyncio
async def test_claimed_creator_can_view_own_insights_and_profile(make_client, make_user):
    agency, ah, creator, ch, cid = await _agency_and_claimed_creator(
        make_client, make_user, agency_email="rtagency5@test.com", creator_email="rtcreator5@test.com")

    # Before claim/fix, this would 404 — the record is tenant-owned by the agency.
    profile = await creator.get(f"/api/matching/creators/{cid}", headers=ch)
    assert profile.status_code == 200, profile.text

    insights = await creator.get(f"/api/matching/creators/{cid}/insights", headers=ch)
    assert insights.status_code == 200, insights.text
    assert insights.json()["subject"]["id"] == cid


@pytest.mark.asyncio
async def test_stranger_still_cannot_view_a_non_discoverable_creators_profile(make_client, make_user):
    agency_creds = await make_user("rtagency6@test.com", "AgencyPass123", Role.admin)
    stranger_creds = await make_user("rtstranger6@test.com", "StrangerPass123", Role.admin)
    agency, stranger = await make_client(), await make_client()
    ah, xh = await _login(agency, **agency_creds), await _login(stranger, **stranger_creds)

    cid = (await agency.post("/api/matching/creators", headers=ah, json={
        "display_name": "Hidden", "discoverable": False})).json()["id"]

    denied_profile = await stranger.get(f"/api/matching/creators/{cid}", headers=xh)
    assert denied_profile.status_code == 404
    denied_insights = await stranger.get(f"/api/matching/creators/{cid}/insights", headers=xh)
    assert denied_insights.status_code == 404


@pytest.mark.asyncio
async def test_unclaimed_creator_still_routes_to_agency(make_client, make_user):
    agency_creds = await make_user("rtagency4@test.com", "AgencyPass123", Role.admin)
    agency = await make_client()
    ah = await _login(agency, **agency_creds)
    cid = (await agency.post("/api/matching/creators", headers=ah, json={
        "display_name": "Never Claimed", "discoverable": True})).json()["id"]

    brand_creds = await make_user("rtbrand4@test.com", "BrandPass123", Role.admin)
    brand = await make_client()
    bh = await _login(brand, **brand_creds)
    pid = (await brand.post("/api/matching/products", headers=bh, json={
        "name": "Staging Co 4", "status": "active", "discoverable": True})).json()["id"]
    rid = (await brand.post("/api/matching/collaborations", headers=bh, json={
        "direction": "brand_to_creator", "creator_id": cid, "product_id": pid,
        "message": "collab?"})).json()["id"]

    agency_inbox = await agency.get("/api/matching/collaborations?box=incoming", headers=ah)
    assert any(x["id"] == rid for x in agency_inbox.json())
