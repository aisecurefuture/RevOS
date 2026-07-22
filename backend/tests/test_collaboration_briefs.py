"""Collaboration briefs + deliverables (CW3) — co-authored brief with
disclosure/usage terms, and milestone tracking."""

from __future__ import annotations

import uuid

import pytest
from app.core.exceptions import RevOSError
from app.models.collaboration import DeliverableStatus
from app.models.matching import CollaborationDirection, CollaborationRequest, CollaborationStatus
from app.models.user import Role
from app.services import workspace_service

ACCT_BRAND = uuid.uuid4()
ACCT_CREATOR = uuid.uuid4()
OTHER = uuid.uuid4()


async def _collaboration(s):
    req = CollaborationRequest(
        direction=CollaborationDirection.brand_to_creator, status=CollaborationStatus.accepted,
        initiator_account_id=ACCT_BRAND, initiator_user_id=uuid.uuid4(),
        recipient_account_id=ACCT_CREATOR, creator_id=uuid.uuid4(), product_id=uuid.uuid4(),
        message="collab?")
    s.add(req)
    await s.flush()
    return await workspace_service.spawn_collaboration(s, req)


@pytest.mark.asyncio
async def test_brief_defaults_require_disclosure(async_session_factory):
    async with async_session_factory() as s:
        collab = await _collaboration(s)
        brief = await workspace_service.upsert_brief(
            s, collab, account_id=ACCT_BRAND, data={
                "goals": "Drive awareness", "key_messages": ["quality", "trust"],
                "dos": ["show the product in use"], "donts": ["no competitor mentions"],
                "deadline": None, "requires_disclosure": True, "disclosure_text": "#ad",
                "usage_rights": "90 days on brand channels", "usage_duration_days": 90,
                "whitelisting_allowed": True, "boost_allowed": False,
            })
        assert brief.requires_disclosure is True
        assert brief.disclosure_text == "#ad"
        assert brief.usage_duration_days == 90
        assert brief.updated_by_account_id == ACCT_BRAND


@pytest.mark.asyncio
async def test_either_party_can_edit_the_shared_brief(async_session_factory):
    async with async_session_factory() as s:
        collab = await _collaboration(s)
        await workspace_service.upsert_brief(
            s, collab, account_id=ACCT_BRAND, data={
                "goals": "v1", "key_messages": [], "dos": [], "donts": [], "deadline": None,
                "requires_disclosure": True, "disclosure_text": None, "usage_rights": None,
                "usage_duration_days": None, "whitelisting_allowed": False, "boost_allowed": False,
            })
        updated = await workspace_service.upsert_brief(
            s, collab, account_id=ACCT_CREATOR, data={
                "goals": "v2 — creator's edit", "key_messages": [], "dos": [], "donts": [],
                "deadline": None, "requires_disclosure": True, "disclosure_text": None,
                "usage_rights": None, "usage_duration_days": None,
                "whitelisting_allowed": False, "boost_allowed": False,
            })
        assert updated.goals == "v2 — creator's edit"
        assert updated.updated_by_account_id == ACCT_CREATOR

        fetched = await workspace_service.get_brief(s, collab, ACCT_BRAND)
        assert fetched.goals == "v2 — creator's edit"   # one shared doc, not per-party copies


@pytest.mark.asyncio
async def test_non_party_cannot_read_or_edit_brief(async_session_factory):
    async with async_session_factory() as s:
        collab = await _collaboration(s)
        with pytest.raises(RevOSError) as exc:
            await workspace_service.get_brief(s, collab, OTHER)
        assert exc.value.code == "forbidden"
        with pytest.raises(RevOSError) as exc2:
            await workspace_service.upsert_brief(s, collab, account_id=OTHER, data={
                "goals": "hack", "key_messages": [], "dos": [], "donts": [], "deadline": None,
                "requires_disclosure": True, "disclosure_text": None, "usage_rights": None,
                "usage_duration_days": None, "whitelisting_allowed": False, "boost_allowed": False,
            })
        assert exc2.value.code == "forbidden"


@pytest.mark.asyncio
async def test_deliverable_lifecycle_and_completion_stamp(async_session_factory):
    async with async_session_factory() as s:
        collab = await _collaboration(s)
        d = await workspace_service.create_deliverable(
            s, collab, created_by_account_id=ACCT_BRAND, title="3 posts + 1 reel",
            description="Launch week content", due_at=None)
        assert d.status == DeliverableStatus.pending and d.completed_at is None

        d = await workspace_service.update_deliverable(
            s, d, collab, account_id=ACCT_CREATOR, data={"status": DeliverableStatus.in_progress})
        assert d.completed_at is None

        d = await workspace_service.update_deliverable(
            s, d, collab, account_id=ACCT_CREATOR, data={"status": DeliverableStatus.approved})
        assert d.completed_at is not None


@pytest.mark.asyncio
async def test_deliverable_can_link_to_an_asset_from_the_same_collaboration(async_session_factory):
    from app.models.collaboration import AssetKind

    async with async_session_factory() as s:
        collab = await _collaboration(s)
        asset = await workspace_service.create_asset(
            s, collab, created_by_account_id=ACCT_BRAND, kind=AssetKind.text, title="Post",
            caption="Draft", media_urls=[])
        d = await workspace_service.create_deliverable(
            s, collab, created_by_account_id=ACCT_BRAND, title="Launch post", description=None,
            due_at=None)
        d = await workspace_service.update_deliverable(
            s, d, collab, account_id=ACCT_BRAND, data={"asset_id": asset.id})
        assert d.asset_id == asset.id


@pytest.mark.asyncio
async def test_deliverable_rejects_asset_from_another_collaboration(async_session_factory):
    from app.models.collaboration import AssetKind

    async with async_session_factory() as s:
        collab1 = await _collaboration(s)
        collab2 = await _collaboration(s)
        other_asset = await workspace_service.create_asset(
            s, collab2, created_by_account_id=ACCT_BRAND, kind=AssetKind.text, title="Other",
            caption="x", media_urls=[])
        d = await workspace_service.create_deliverable(
            s, collab1, created_by_account_id=ACCT_BRAND, title="Task", description=None, due_at=None)
        with pytest.raises(RevOSError) as exc:
            await workspace_service.update_deliverable(
                s, d, collab1, account_id=ACCT_BRAND, data={"asset_id": other_asset.id})
        assert exc.value.code == "invalid_asset"


# --- HTTP smoke test ---------------------------------------------------------
async def _login(client, email, password):
    r = await client.post("/api/auth/login", json={"email": email, "password": password})
    return {"X-CSRF-Token": r.json()["csrf_token"]}


@pytest.mark.asyncio
async def test_brief_and_deliverables_over_http(make_client, make_user):
    brand_creds = await make_user("bbrief@test.com", "BrandPass123", Role.admin)
    creator_creds = await make_user("cbrief@test.com", "CreatorPass123", Role.admin)
    brand, creator = await make_client(), await make_client()
    bh, ch = await _login(brand, **brand_creds), await _login(creator, **creator_creds)

    cid = (await creator.post("/api/matching/creators", headers=ch, json={
        "display_name": "Ava", "handle": "@avabrief", "discoverable": True})).json()["id"]
    pid = (await brand.post("/api/matching/products", headers=bh, json={
        "name": "Staging Co", "status": "active", "discoverable": True})).json()["id"]
    rid = (await brand.post("/api/matching/collaborations", headers=bh, json={
        "direction": "brand_to_creator", "creator_id": cid, "product_id": pid,
        "message": "collab?"})).json()["id"]
    await creator.post(f"/api/matching/collaborations/{rid}/respond", headers=ch, json={"accept": True})
    wid = (await brand.get("/api/matching/workspaces", headers=bh)).json()[0]["id"]

    # No brief yet.
    empty = await brand.get(f"/api/matching/workspaces/{wid}/brief", headers=bh)
    assert empty.status_code == 200 and empty.json() is None

    put1 = await brand.put(f"/api/matching/workspaces/{wid}/brief", headers=bh, json={
        "goals": "Drive launch awareness", "key_messages": ["quality"], "dos": [], "donts": [],
        "requires_disclosure": True, "disclosure_text": "#ad", "whitelisting_allowed": True,
        "boost_allowed": False})
    assert put1.status_code == 200 and put1.json()["disclosure_text"] == "#ad"

    got = await creator.get(f"/api/matching/workspaces/{wid}/brief", headers=ch)
    assert got.json()["goals"] == "Drive launch awareness"

    d = await creator.post(f"/api/matching/workspaces/{wid}/deliverables", headers=ch, json={
        "title": "3 posts + 1 reel", "description": "Launch week"})
    assert d.status_code == 201
    did = d.json()["id"]

    upd = await brand.patch(f"/api/matching/workspaces/{wid}/deliverables/{did}", headers=bh,
                            json={"status": "approved"})
    assert upd.status_code == 200 and upd.json()["status"] == "approved"
    assert upd.json()["completed_at"] is not None

    listed = await creator.get(f"/api/matching/workspaces/{wid}/deliverables", headers=ch)
    assert len(listed.json()) == 1
