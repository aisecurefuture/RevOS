"""Reputation RK2 — endpoint aggregates reviews + certs + collaboration history."""

from __future__ import annotations

import uuid

import pytest
from app.models.base import utcnow
from app.models.matching import (
    CollaborationDirection,
    CollaborationRequest,
    CollaborationStatus,
    Creator,
    CreatorStatus,
)
from app.models.reputation import (
    Certification,
    CertificationSubjectType,
    Review,
    ReviewDirection,
)
from app.models.user import Role


async def _login(api, make_user):
    creds = await make_user("viewer@test.com", "ViewerPass123", Role.admin)
    r = await api.post("/api/auth/login", json=creds)
    return {"X-CSRF-Token": r.json()["csrf_token"]}


async def _seed_reviewed_creator(session_factory, *, account_id, discoverable=True,
                                 ratings=(5, 5, 5, 5, 4), verified_certs=1):
    async with session_factory() as s:
        c = Creator(display_name="Rep Star", account_id=account_id,
                    status=CreatorStatus.active, discoverable=discoverable)
        s.add(c)
        await s.flush()
        for rating in ratings:
            collab = CollaborationRequest(
                direction=CollaborationDirection.brand_to_creator,
                status=CollaborationStatus.accepted,          # received + responded
                initiator_account_id=uuid.uuid4(), initiator_user_id=uuid.uuid4(),
                creator_id=c.id, recipient_account_id=account_id, message="x")
            s.add(collab)
            await s.flush()
            s.add(Review(
                collaboration_request_id=collab.id, direction=ReviewDirection.brand_reviews_creator,
                reviewer_account_id=collab.initiator_account_id, reviewer_user_id=uuid.uuid4(),
                subject_creator_id=c.id, rating=rating))
        for _ in range(verified_certs):
            s.add(Certification(account_id=account_id, subject_type=CertificationSubjectType.creator,
                                subject_id=c.id, name="Licensed Realtor", verified=True))
        await s.commit()
        return c.id


@pytest.mark.asyncio
async def test_creator_reputation_aggregates_all_signals(api, make_user, async_session_factory):
    h = await _login(api, make_user)
    cid = await _seed_reviewed_creator(async_session_factory, account_id=uuid.uuid4())

    resp = await api.get(f"/api/matching/creators/{cid}/reputation", headers=h)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["review_count"] == 5
    assert {d["key"] for d in body["dimensions"]} == {
        "review_reputation", "reliability", "certifications"}
    # reviews present + all 5 accepted (perfect responsiveness) + 1 verified cert
    assert body["coverage"] == pytest.approx(1.0)
    assert body["overall"] > 65
    rel = next(d for d in body["dimensions"] if d["key"] == "reliability")
    assert rel["available"] and rel["score"] == pytest.approx(100, abs=0.1)


@pytest.mark.asyncio
async def test_reputation_hidden_for_non_discoverable_other_tenant(api, make_user, async_session_factory):
    h = await _login(api, make_user)
    cid = await _seed_reviewed_creator(async_session_factory, account_id=uuid.uuid4(),
                                       discoverable=False)
    resp = await api.get(f"/api/matching/creators/{cid}/reputation", headers=h)
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_reputation_missing_creator_404(api, make_user):
    h = await _login(api, make_user)
    resp = await api.get(f"/api/matching/creators/{uuid.uuid4()}/reputation", headers=h)
    assert resp.status_code == 404
