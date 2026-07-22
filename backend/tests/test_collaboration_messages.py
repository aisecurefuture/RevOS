"""Collaboration messages (Phase 6) — full threads, report, and the
end-collaboration-as-block behavior."""

from __future__ import annotations

import uuid

import pytest
from app.core.exceptions import RevOSError
from app.models.matching import CollaborationDirection, CollaborationRequest, CollaborationStatus
from app.models.user import Role
from app.services import workspace_service

ACCT_BRAND = uuid.uuid4()
ACCT_CREATOR = uuid.uuid4()
USER_BRAND = uuid.uuid4()
USER_CREATOR = uuid.uuid4()
OTHER = uuid.uuid4()


async def _collaboration(s):
    req = CollaborationRequest(
        direction=CollaborationDirection.brand_to_creator, status=CollaborationStatus.accepted,
        initiator_account_id=ACCT_BRAND, initiator_user_id=USER_BRAND,
        recipient_account_id=ACCT_CREATOR, creator_id=uuid.uuid4(), product_id=uuid.uuid4(),
        message="collab?")
    s.add(req)
    await s.flush()
    return await workspace_service.spawn_collaboration(s, req)


@pytest.mark.asyncio
async def test_both_parties_can_send_and_see_messages(async_session_factory):
    async with async_session_factory() as s:
        collab = await _collaboration(s)
        await workspace_service.send_message(
            s, collab, sender_account_id=ACCT_BRAND, sender_user_id=USER_BRAND, body="Excited to work together!")
        await workspace_service.send_message(
            s, collab, sender_account_id=ACCT_CREATOR, sender_user_id=USER_CREATOR, body="Likewise!")
        messages = await workspace_service.list_messages(s, collab, ACCT_BRAND)
        assert [m.body for m in messages] == ["Excited to work together!", "Likewise!"]


@pytest.mark.asyncio
async def test_non_party_cannot_send_or_read(async_session_factory):
    async with async_session_factory() as s:
        collab = await _collaboration(s)
        with pytest.raises(RevOSError) as exc:
            await workspace_service.send_message(
                s, collab, sender_account_id=OTHER, sender_user_id=uuid.uuid4(), body="hi")
        assert exc.value.code == "forbidden"
        with pytest.raises(RevOSError) as exc2:
            await workspace_service.list_messages(s, collab, OTHER)
        assert exc2.value.code == "forbidden"


@pytest.mark.asyncio
async def test_ending_collaboration_blocks_new_messages(async_session_factory):
    async with async_session_factory() as s:
        collab = await _collaboration(s)
        await workspace_service.send_message(
            s, collab, sender_account_id=ACCT_BRAND, sender_user_id=USER_BRAND, body="before end")
        await workspace_service.end_collaboration(s, collab, ACCT_CREATOR)

        with pytest.raises(RevOSError) as exc:
            await workspace_service.send_message(
                s, collab, sender_account_id=ACCT_BRAND, sender_user_id=USER_BRAND, body="after end")
        assert exc.value.code == "collaboration_ended"

        # But the existing thread is still readable.
        messages = await workspace_service.list_messages(s, collab, ACCT_CREATOR)
        assert len(messages) == 1


@pytest.mark.asyncio
async def test_report_flags_message_and_records_reporter(async_session_factory):
    async with async_session_factory() as s:
        collab = await _collaboration(s)
        msg = await workspace_service.send_message(
            s, collab, sender_account_id=ACCT_BRAND, sender_user_id=USER_BRAND, body="rude thing")
        reported = await workspace_service.report_message(
            s, msg, collab, reporter_account_id=ACCT_CREATOR, reason="Inappropriate language")
        assert reported.is_flagged is True
        assert reported.flagged_by_account_id == ACCT_CREATOR
        assert reported.flagged_reason == "Inappropriate language"
        assert reported.flagged_at is not None


@pytest.mark.asyncio
async def test_cannot_report_own_message(async_session_factory):
    async with async_session_factory() as s:
        collab = await _collaboration(s)
        msg = await workspace_service.send_message(
            s, collab, sender_account_id=ACCT_BRAND, sender_user_id=USER_BRAND, body="my own words")
        with pytest.raises(RevOSError) as exc:
            await workspace_service.report_message(
                s, msg, collab, reporter_account_id=ACCT_BRAND, reason="self-report attempt")
        assert exc.value.code == "forbidden"


@pytest.mark.asyncio
async def test_non_party_cannot_report(async_session_factory):
    async with async_session_factory() as s:
        collab = await _collaboration(s)
        msg = await workspace_service.send_message(
            s, collab, sender_account_id=ACCT_BRAND, sender_user_id=USER_BRAND, body="hello")
        with pytest.raises(RevOSError) as exc:
            await workspace_service.report_message(
                s, msg, collab, reporter_account_id=OTHER, reason="spam")
        assert exc.value.code == "forbidden"


# --- HTTP smoke test ---------------------------------------------------------
async def _login(client, email, password):
    r = await client.post("/api/auth/login", json={"email": email, "password": password})
    return {"X-CSRF-Token": r.json()["csrf_token"]}


@pytest.mark.asyncio
async def test_full_messaging_flow_over_http(make_client, make_user):
    brand_creds = await make_user("mbrand@test.com", "BrandPass123", Role.admin)
    creator_creds = await make_user("mcreator@test.com", "CreatorPass123", Role.admin)
    brand, creator = await make_client(), await make_client()
    bh, ch = await _login(brand, **brand_creds), await _login(creator, **creator_creds)

    cid = (await creator.post("/api/matching/creators", headers=ch, json={
        "display_name": "Ava", "handle": "@avamsg", "discoverable": True})).json()["id"]
    pid = (await brand.post("/api/matching/products", headers=bh, json={
        "name": "Staging Co", "status": "active", "discoverable": True})).json()["id"]
    rid = (await brand.post("/api/matching/collaborations", headers=bh, json={
        "direction": "brand_to_creator", "creator_id": cid, "product_id": pid,
        "message": "collab?"})).json()["id"]
    await creator.post(f"/api/matching/collaborations/{rid}/respond", headers=ch, json={"accept": True})
    wid = (await brand.get("/api/matching/workspaces", headers=bh)).json()[0]["id"]

    m1 = await brand.post(f"/api/matching/workspaces/{wid}/messages", headers=bh,
                          json={"body": "Hi! Excited to collaborate."})
    assert m1.status_code == 201, m1.text
    await creator.post(f"/api/matching/workspaces/{wid}/messages", headers=ch,
                       json={"body": "Me too! When do we start?"})

    thread = await creator.get(f"/api/matching/workspaces/{wid}/messages", headers=ch)
    assert len(thread.json()) == 2

    # Creator reports the brand's message.
    reported = await creator.post(
        f"/api/matching/workspaces/{wid}/messages/{m1.json()['id']}/report", headers=ch,
        json={"reason": "Off-topic spam"})
    assert reported.status_code == 200 and reported.json()["is_flagged"] is True

    # Ending the collaboration blocks further messages.
    await brand.post(f"/api/matching/workspaces/{wid}/end", headers=bh)
    blocked = await brand.post(f"/api/matching/workspaces/{wid}/messages", headers=bh,
                               json={"body": "one more thing"})
    assert blocked.status_code == 403
    assert blocked.json()["error"]["code"] == "collaboration_ended"
