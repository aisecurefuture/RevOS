"""BM2 — blending third-party industry benchmarks into the existing insights
+ public-page logic: RevOS's own peer cohort first, curated industry-report
figure as the fallback when the cohort is too thin. Every result says which."""

from __future__ import annotations

import uuid

import pytest
from app.models.base import utcnow
from app.models.matching import Creator, CreatorStatus
from app.services import benchmark_service, insights_service


async def _creator(s, *, account_id=None, industry="real_estate_agent", size_tier="micro",
                   engagement_rate=0.05, primary_platform="instagram", display_name="Ava", **kw):
    c = Creator(display_name=display_name, account_id=account_id or uuid.uuid4(), status=CreatorStatus.active,
               industry=industry, size_tier=size_tier, engagement_rate=engagement_rate,
               primary_platform=primary_platform, **kw)
    s.add(c)
    await s.flush()
    return c


@pytest.mark.asyncio
async def test_falls_back_to_industry_report_when_cohort_too_thin(async_session_factory):
    async with async_session_factory() as s:
        subject = await _creator(s)   # no peers at all — thin cohort
        await benchmark_service.create(s, {
            "industry_category": "real_estate", "platform": "instagram", "value": 0.03,
            "source": "Quid 2026 Social Media Industry Benchmark Report", "period_label": "2026 Annual",
        }, updated_by_user_id=uuid.uuid4())

        result = await insights_service.engagement_benchmark(s, subject)

    assert result is not None
    assert result["source"] == "industry_report"
    assert result["cohort_avg"] == 0.03
    assert "Quid 2026" in result["citation"] and "2026 Annual" in result["citation"]
    assert result["percentile"] is None   # can't compute a percentile against a report
    assert result["verdict"] == "above"   # 0.05 vs 0.03


@pytest.mark.asyncio
async def test_prefers_revos_cohort_when_sufficient(async_session_factory):
    async with async_session_factory() as s:
        for i in range(4):
            await _creator(s, engagement_rate=0.02, display_name=f"peer{i}")
        subject = await _creator(s, engagement_rate=0.06)
        await benchmark_service.create(s, {
            "industry_category": "real_estate", "platform": "instagram", "value": 0.03,
            "source": "Quid report", "period_label": "2026",
        }, updated_by_user_id=uuid.uuid4())

        result = await insights_service.engagement_benchmark(s, subject)

    assert result["source"] == "revos_cohort"   # real peers exist — industry report NOT used
    assert result["citation"] is None
    assert result["percentile"] is not None


@pytest.mark.asyncio
async def test_no_fallback_available_returns_none(async_session_factory):
    async with async_session_factory() as s:
        subject = await _creator(s, industry=None)   # no industry → can't look up a report either
        result = await insights_service.engagement_benchmark(s, subject)
    assert result is None


@pytest.mark.asyncio
async def test_no_engagement_rate_returns_none_regardless_of_benchmarks(async_session_factory):
    async with async_session_factory() as s:
        subject = await _creator(s, engagement_rate=None)
        await benchmark_service.create(s, {
            "industry_category": "real_estate", "value": 0.03, "source": "x", "period_label": "2026",
        }, updated_by_user_id=uuid.uuid4())
        result = await insights_service.engagement_benchmark(s, subject)
    assert result is None


@pytest.mark.asyncio
async def test_follower_benchmark_stays_cohort_only_no_industry_fallback(async_session_factory):
    """Follower count has no third-party-report equivalent — a thin cohort
    should just omit it, never fabricate a number."""
    async with async_session_factory() as s:
        subject = await _creator(s, follower_count=1000)
        result = await insights_service.creator_insights(s, subject, now=utcnow())
    assert all(b["metric"] != "follower_count" for b in result["benchmarks"])


# --- Public page surfacing ---------------------------------------------------
async def _login(client, email, password):
    r = await client.post("/api/auth/login", json={"email": email, "password": password})
    return {"X-CSRF-Token": r.json()["csrf_token"]}


@pytest.mark.asyncio
async def test_public_page_surfaces_cited_industry_benchmark(make_client, make_user, monkeypatch):
    from app.config import settings as app_settings
    from app.models.user import Role

    monkeypatch.setattr(app_settings, "platform_admin_emails", "bmadmin@test.com")
    admin_creds = await make_user("bmadmin@test.com", "AdminPass12345", Role.admin)
    creator_creds = await make_user("bmpub1@test.com", "PubPass12345", Role.admin)
    admin, client = await make_client(), await make_client()
    ah, h = await _login(admin, **admin_creds), await _login(client, **creator_creds)

    await admin.post("/api/benchmarks", headers=ah, json={
        "industry_category": "real_estate", "platform": "instagram", "value": 0.03,
        "source": "Quid 2026 Social Media Industry Benchmark Report", "period_label": "2026 Annual",
    })

    cid = (await client.post("/api/matching/creators", headers=h, json={
        "display_name": "Ava", "industry": "real_estate_agent", "primary_platform": "instagram",
        "engagement_rate": 0.05,
    })).json()["id"]
    await client.patch(f"/api/matching/creators/{cid}/public-page", headers=h, json={
        "enabled": True, "fields": ["engagement_rate"]})
    slug = (await client.get(f"/api/matching/creators/{cid}/public-page", headers=h)).json()["slug"]

    public = await client.get(f"/api/public/creators/{slug}")
    body = public.json()
    assert body["engagement_rate"] == 0.05
    assert body["engagement_benchmark"]["source"] == "industry_report"
    assert "Quid 2026" in body["engagement_benchmark"]["citation"]


@pytest.mark.asyncio
async def test_engagement_rate_field_without_a_benchmark_returns_null_not_an_error(make_client, make_user):
    from app.models.user import Role

    creds = await make_user("bmpub2@test.com", "PubPass12345", Role.admin)
    client = await make_client()
    h = await _login(client, **creds)
    cid = (await client.post("/api/matching/creators", headers=h, json={
        "display_name": "Ava2", "engagement_rate": 0.05,   # no industry set — nothing to compare against
    })).json()["id"]
    await client.patch(f"/api/matching/creators/{cid}/public-page", headers=h, json={
        "enabled": True, "fields": ["engagement_rate"]})
    slug = (await client.get(f"/api/matching/creators/{cid}/public-page", headers=h)).json()["slug"]

    public = await client.get(f"/api/public/creators/{slug}")
    assert public.status_code == 200
    assert public.json()["engagement_benchmark"] is None
