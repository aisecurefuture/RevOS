"""Creator-portal groundwork (Phase 6) — claim invites, self-service claim,
and the read-only "claimed by me" listing. Ownership stays with the managing
tenant; claiming only grants the verifying user their own identity link."""

from __future__ import annotations

import pytest
from app.core.exceptions import AuthError, RevOSError
from app.models.user import Role
from app.services import creator_service


async def _login(client, email, password):
    r = await client.post("/api/auth/login", json={"email": email, "password": password})
    return {"X-CSRF-Token": r.json()["csrf_token"]}


@pytest.mark.asyncio
async def test_only_owner_can_generate_claim_invite(make_client, make_user):
    owner_creds = await make_user("agency@test.com", "AgencyPass123", Role.admin)
    other_creds = await make_user("other@test.com", "OtherPass123", Role.admin)
    owner, other = await make_client(), await make_client()
    oh, xh = await _login(owner, **owner_creds), await _login(other, **other_creds)

    cid = (await owner.post("/api/matching/creators", headers=oh, json={
        "display_name": "Ava"})).json()["id"]

    denied = await other.post(f"/api/matching/creators/{cid}/claim-invite", headers=xh)
    assert denied.status_code == 404   # tenant-scoped: not visible to a non-owner at all

    ok = await owner.post(f"/api/matching/creators/{cid}/claim-invite", headers=oh)
    assert ok.status_code == 200, ok.text
    assert ok.json()["token"] and "token=" in ok.json()["claim_url"]


@pytest.mark.asyncio
async def test_full_claim_flow_over_http(make_client, make_user):
    agency_creds = await make_user("agency2@test.com", "AgencyPass123", Role.admin)
    creator_creds = await make_user("realcreator@test.com", "RealPass1234", Role.admin)
    agency, creator = await make_client(), await make_client()
    ah, ch = await _login(agency, **agency_creds), await _login(creator, **creator_creds)

    cid = (await agency.post("/api/matching/creators", headers=ah, json={
        "display_name": "Ava (managed)"})).json()["id"]
    invite = (await agency.post(f"/api/matching/creators/{cid}/claim-invite", headers=ah)).json()

    claimed = await creator.post("/api/matching/creators/claim", headers=ch,
                                 json={"token": invite["token"]})
    assert claimed.status_code == 200, claimed.text
    assert claimed.json()["claimed_by_user_id"] is not None
    assert claimed.json()["claimed_at"] is not None

    mine = await creator.get("/api/matching/creators/claimed/mine", headers=ch)
    assert any(c["id"] == cid for c in mine.json())

    # The agency still owns/manages the record — tenant ownership is untouched.
    still_theirs = await agency.get(f"/api/matching/creators/{cid}", headers=ah)
    assert still_theirs.status_code == 200


@pytest.mark.asyncio
async def test_reclaiming_by_the_same_user_is_idempotent(make_client, make_user):
    agency_creds = await make_user("agency3@test.com", "AgencyPass123", Role.admin)
    creator_creds = await make_user("creator3@test.com", "CreatorPass123", Role.admin)
    agency, creator = await make_client(), await make_client()
    ah, ch = await _login(agency, **agency_creds), await _login(creator, **creator_creds)

    cid = (await agency.post("/api/matching/creators", headers=ah, json={
        "display_name": "Ava3"})).json()["id"]
    invite = (await agency.post(f"/api/matching/creators/{cid}/claim-invite", headers=ah)).json()

    first = await creator.post("/api/matching/creators/claim", headers=ch, json={"token": invite["token"]})
    second = await creator.post("/api/matching/creators/claim", headers=ch, json={"token": invite["token"]})
    assert first.status_code == 200 and second.status_code == 200
    assert first.json()["claimed_at"] is not None


@pytest.mark.asyncio
async def test_second_user_cannot_claim_an_already_claimed_creator(make_client, make_user):
    agency_creds = await make_user("agency4@test.com", "AgencyPass123", Role.admin)
    first_creds = await make_user("first4@test.com", "FirstPass123", Role.admin)
    second_creds = await make_user("second4@test.com", "SecondPass123", Role.admin)
    agency, first, second = await make_client(), await make_client(), await make_client()
    ah = await _login(agency, **agency_creds)
    fh = await _login(first, **first_creds)
    sh = await _login(second, **second_creds)

    cid = (await agency.post("/api/matching/creators", headers=ah, json={
        "display_name": "Ava4"})).json()["id"]
    invite = (await agency.post(f"/api/matching/creators/{cid}/claim-invite", headers=ah)).json()

    await first.post("/api/matching/creators/claim", headers=fh, json={"token": invite["token"]})
    conflict = await second.post("/api/matching/creators/claim", headers=sh, json={"token": invite["token"]})
    assert conflict.status_code == 409
    assert conflict.json()["error"]["code"] == "already_claimed"


@pytest.mark.asyncio
async def test_tampered_token_is_rejected(async_session_factory):
    async with async_session_factory() as s:
        with pytest.raises(AuthError):
            await creator_service.claim_creator(s, "not-a-real-token", user_id=__import__("uuid").uuid4())


@pytest.mark.asyncio
async def test_claiming_a_deleted_creator_fails(async_session_factory):
    import uuid as _uuid

    async with async_session_factory() as s:
        token_data = creator_service.make_claim_invite(_uuid.uuid4())  # random, never-created id
        with pytest.raises(RevOSError) as exc:
            await creator_service.claim_creator(s, token_data["token"], user_id=_uuid.uuid4())
        assert exc.value.code == "not_found"
