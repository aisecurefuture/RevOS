"""Live insights aggregation (Phase 6) — flag gate, weighted averaging across
connections, and one-platform-failure-doesn't-block-others resilience."""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock

import pytest
from app.models.matching import Creator, CreatorStatus
from app.models.social import SocialPlatform
from app.models.social_connection import SocialConnection, SocialConnectionStatus
from app.services import live_insights_service as svc
from app.services.social.base import AudienceStats


async def _creator_with_connections(s, *connections):
    creator = Creator(display_name="Ava", account_id=uuid.uuid4(), status=CreatorStatus.active,
                      follower_count=0)
    s.add(creator)
    await s.flush()
    for platform, external_id in connections:
        s.add(SocialConnection(
            account_id=creator.account_id, creator_id=creator.id, platform=platform,
            external_id=external_id, status=SocialConnectionStatus.active,
            token_ref=f"kv/{external_id}", connected_by=uuid.uuid4(),
        ))
    await s.flush()
    return creator


@pytest.mark.asyncio
async def test_ingest_all_disabled_by_default(async_session_factory):
    async with async_session_factory() as s:
        result = await svc.ingest_all(s)
    assert result == {"enabled": False, "creators_checked": 0, "creators_updated": 0}


@pytest.mark.asyncio
async def test_ingest_for_creator_no_connections_is_a_noop(async_session_factory):
    async with async_session_factory() as s:
        creator = Creator(display_name="Solo", account_id=uuid.uuid4(), status=CreatorStatus.active)
        s.add(creator)
        await s.flush()
        result = await svc.ingest_for_creator(s, creator)
    assert result == {"updated": False, "platforms": 0}


@pytest.mark.asyncio
async def test_ingest_aggregates_followers_and_weighted_engagement(async_session_factory, monkeypatch):
    async with async_session_factory() as s:
        creator = await _creator_with_connections(
            s, (SocialPlatform.instagram, "ig1"), (SocialPlatform.youtube, "yt1"))

        monkeypatch.setattr(svc, "_token_data", AsyncMock(return_value={"access_token": "T"}))

        async def fake_fetch(conn):
            if conn.platform == SocialPlatform.instagram:
                return AudienceStats(follower_count=1000, engagement_rate=0.10)
            return AudienceStats(follower_count=3000, engagement_rate=0.02)
        monkeypatch.setattr(svc, "_fetch_for_connection", fake_fetch)

        result = await svc.ingest_for_creator(s, creator)

    assert result["updated"] is True
    assert result["follower_count"] == 4000
    assert creator.follower_count == 4000
    # weighted by followers: (1000*0.10 + 3000*0.02) / 4000
    assert creator.engagement_rate == pytest.approx((100 + 60) / 4000)
    assert creator.audience_source == "connected"
    assert creator.audience_captured_at is not None
    assert creator.size_tier == "nano"   # 4000 followers


@pytest.mark.asyncio
async def test_one_platform_failure_does_not_block_others(async_session_factory, monkeypatch):
    async with async_session_factory() as s:
        creator = await _creator_with_connections(
            s, (SocialPlatform.tiktok, "tt1"), (SocialPlatform.linkedin, "li1"))

        async def fake_fetch(conn):
            if conn.platform == SocialPlatform.tiktok:
                return AudienceStats(follower_count=500, engagement_rate=None)
            return None   # LinkedIn: documented no-op
        monkeypatch.setattr(svc, "_fetch_for_connection", fake_fetch)

        result = await svc.ingest_for_creator(s, creator)

    assert result["updated"] is True
    assert result["follower_count"] == 500
    assert creator.engagement_rate is None   # untouched — no platform returned an engagement rate


@pytest.mark.asyncio
async def test_all_platforms_failing_leaves_creator_unchanged(async_session_factory, monkeypatch):
    async with async_session_factory() as s:
        creator = await _creator_with_connections(s, (SocialPlatform.linkedin, "li1"))
        monkeypatch.setattr(svc, "_fetch_for_connection", AsyncMock(return_value=None))
        result = await svc.ingest_for_creator(s, creator)
    assert result == {"updated": False, "platforms": 0}


@pytest.mark.asyncio
async def test_ingest_all_enabled_processes_creators_with_active_connections(
    async_session_factory, monkeypatch,
):
    monkeypatch.setattr(svc.settings, "live_insights_ingestion_enabled", True)
    async with async_session_factory() as s:
        creator = await _creator_with_connections(s, (SocialPlatform.instagram, "ig1"))
        monkeypatch.setattr(svc, "_fetch_for_connection", AsyncMock(
            return_value=AudienceStats(follower_count=250, engagement_rate=0.05)))

        result = await svc.ingest_all(s)

    assert result["enabled"] is True
    assert result["creators_checked"] == 1
    assert result["creators_updated"] == 1
