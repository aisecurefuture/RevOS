"""Insight dashboards (IK1) — benchmarked metrics + recommendations."""

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
from app.models.reputation import Review, ReviewDirection
from app.models.user import Role
from app.services import insights_service

ACCT = uuid.uuid4()


async def _creator(s, *, account_id=ACCT, discoverable=True, industry="real_estate_agent",
                   size_tier="micro", engagement_rate=0.05, follower_count=40_000,
                   display_name="Subject", **kw):
    c = Creator(display_name=display_name, account_id=account_id, status=CreatorStatus.active,
                discoverable=discoverable, industry=industry, size_tier=size_tier,
                engagement_rate=engagement_rate, follower_count=follower_count, **kw)
    s.add(c)
    await s.flush()
    await s.refresh(c)
    return c


async def _accepted_with_review(s, creator, *, rating, respond=True):
    collab = CollaborationRequest(
        direction=CollaborationDirection.brand_to_creator,
        status=CollaborationStatus.accepted if respond else CollaborationStatus.expired,
        initiator_account_id=uuid.uuid4(), initiator_user_id=uuid.uuid4(),
        creator_id=creator.id, recipient_account_id=creator.account_id, message="x",
        expires_at=utcnow())
    s.add(collab)
    await s.flush()
    if respond:
        s.add(Review(collaboration_request_id=collab.id,
                     direction=ReviewDirection.brand_reviews_creator,
                     reviewer_account_id=collab.initiator_account_id, reviewer_user_id=uuid.uuid4(),
                     subject_creator_id=creator.id, rating=rating))
    await s.flush()
    return collab


@pytest.mark.asyncio
async def test_creator_insights_benchmarks_against_cohort(async_session_factory):
    async with async_session_factory() as s:
        # A cohort of same-industry, same-size peers with lower engagement.
        for i in range(6):
            await _creator(s, account_id=uuid.uuid4(), engagement_rate=0.03,
                           follower_count=30_000, display_name=f"peer{i}")
        subject = await _creator(s, engagement_rate=0.06, follower_count=45_000)
        await _accepted_with_review(s, subject, rating=5)

        result = await insights_service.creator_insights(s, subject, now=utcnow())

        eng = next(b for b in result["benchmarks"] if b["metric"] == "engagement_rate")
        assert eng["verdict"] == "above"                # 0.06 vs ~0.033 cohort avg
        assert eng["cohort_size"] >= 7
        assert eng["percentile"] >= 80                  # beats the low-engagement peers
        assert result["metrics"]["review_count"] == 1
        assert result["metrics"]["avg_rating"] == 5.0
        assert result["reputation"]["overall"] > 0


@pytest.mark.asyncio
async def test_benchmark_suppressed_for_tiny_cohort(async_session_factory):
    async with async_session_factory() as s:
        subject = await _creator(s, industry="veterinarian", size_tier="mega")
        result = await insights_service.creator_insights(s, subject, now=utcnow())
        assert result["benchmarks"] == []              # no peers → no misleading benchmark


@pytest.mark.asyncio
async def test_recommendations_flag_ghosting_and_missing_reviews(async_session_factory):
    async with async_session_factory() as s:
        subject = await _creator(s, discoverable=True)
        # Received 4 actionable requests, only responded to 1 → 25% response rate.
        await _accepted_with_review(s, subject, rating=5, respond=True)
        for _ in range(3):
            await _accepted_with_review(s, subject, rating=0, respond=False)  # expired = ghosted

        result = await insights_service.creator_insights(s, subject, now=utcnow())
        titles = [r["title"] for r in result["recommendations"]]
        assert "Respond to more requests" in titles
        highs = [r for r in result["recommendations"] if r["priority"] == "high"]
        assert highs  # at least one high-priority action


@pytest.mark.asyncio
async def test_hidden_creator_gets_discoverability_recommendation(async_session_factory):
    async with async_session_factory() as s:
        subject = await _creator(s, discoverable=False)
        result = await insights_service.creator_insights(s, subject, now=utcnow())
        titles = [r["title"] for r in result["recommendations"]]
        assert "Turn on discoverability" in titles


@pytest.mark.asyncio
async def test_insights_endpoint_own_only(make_client, make_user, async_session_factory):
    creds = await make_user("owner@test.com", "OwnerPass123", Role.admin)
    client = await make_client()
    r = await client.post("/api/auth/login", json=creds)
    h = {"X-CSRF-Token": r.json()["csrf_token"]}

    # A creator in someone else's account — the endpoint must not expose it.
    async with async_session_factory() as s:
        other = await _creator(s, account_id=uuid.uuid4())
        await s.commit()
        other_id = other.id

    resp = await client.get(f"/api/matching/creators/{other_id}/insights", headers=h)
    assert resp.status_code == 404   # tenant-scoped: not your creator

    # Your own creator returns a dashboard.
    mine = (await client.post("/api/matching/creators", headers=h, json={
        "display_name": "Mine", "industry": "real_estate_agent", "follower_count": 20000,
        "engagement_rate": 0.04})).json()
    ok = await client.get(f"/api/matching/creators/{mine['id']}/insights", headers=h)
    assert ok.status_code == 200, ok.text
    body = ok.json()
    assert body["subject"]["type"] == "creator"
    assert "recommendations" in body and "reputation" in body
