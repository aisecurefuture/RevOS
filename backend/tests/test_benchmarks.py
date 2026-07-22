"""Third-party industry benchmarks (BM1) — admin-only CRUD + the
category/platform/metric lookup with cross-platform fallback."""

from __future__ import annotations

import pytest
from app.services import benchmark_service


async def _register(api, email="user@test.com", pw="PassWord1234", name="User"):
    r = await api.post("/api/auth/register", json={"email": email, "password": pw, "full_name": name})
    assert r.status_code == 201, r.text
    return {"X-CSRF-Token": r.json()["csrf_token"]}


def _make_admin(monkeypatch, *emails):
    from app.config import settings as app_settings
    monkeypatch.setattr(app_settings, "platform_admin_emails", ",".join(emails))


@pytest.mark.asyncio
async def test_non_admin_cannot_read_or_write(api):
    h = await _register(api, "nobody@test.com")
    assert (await api.get("/api/benchmarks", headers=h)).status_code == 403
    assert (await api.post("/api/benchmarks", headers=h, json={
        "industry_category": "real_estate", "value": 0.02, "source": "x", "period_label": "2026"
    })).status_code == 403


@pytest.mark.asyncio
async def test_admin_can_create_and_list(api, monkeypatch):
    _make_admin(monkeypatch, "boss@test.com")
    h = await _register(api, "boss@test.com")
    created = await api.post("/api/benchmarks", headers=h, json={
        "industry_category": "real_estate", "platform": "instagram", "value": 0.021,
        "source": "Quid 2026 Social Media Industry Benchmark Report",
        "source_url": "https://www.quid.com/knowledge-hub/resource-library/blog/2026-social-media-industry-benchmark-report",
        "period_label": "2026 Annual",
    })
    assert created.status_code == 201, created.text
    listed = await api.get("/api/benchmarks", headers=h)
    assert len(listed.json()) == 1
    assert listed.json()[0]["metric"] == "engagement_rate"   # default


@pytest.mark.asyncio
async def test_invalid_industry_category_rejected(api, monkeypatch):
    _make_admin(monkeypatch, "boss2@test.com")
    h = await _register(api, "boss2@test.com")
    resp = await api.post("/api/benchmarks", headers=h, json={
        "industry_category": "not_a_real_category", "value": 0.02, "source": "x", "period_label": "2026"
    })
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_invalid_platform_rejected(api, monkeypatch):
    _make_admin(monkeypatch, "boss3@test.com")
    h = await _register(api, "boss3@test.com")
    resp = await api.post("/api/benchmarks", headers=h, json={
        "industry_category": "real_estate", "platform": "myspace", "value": 0.02,
        "source": "x", "period_label": "2026"
    })
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_duplicate_period_is_rejected_by_unique_constraint(api, monkeypatch):
    _make_admin(monkeypatch, "boss4@test.com")
    h = await _register(api, "boss4@test.com")
    payload = {"industry_category": "real_estate", "platform": "instagram", "value": 0.02,
              "source": "x", "period_label": "2026 Annual"}
    ok = await api.post("/api/benchmarks", headers=h, json=payload)
    assert ok.status_code == 201
    dupe = await api.post("/api/benchmarks", headers=h, json=payload)
    assert dupe.status_code == 409
    assert dupe.json()["error"]["code"] == "duplicate_benchmark"


@pytest.mark.asyncio
async def test_admin_can_delete(api, monkeypatch):
    _make_admin(monkeypatch, "boss5@test.com")
    h = await _register(api, "boss5@test.com")
    created = (await api.post("/api/benchmarks", headers=h, json={
        "industry_category": "real_estate", "value": 0.02, "source": "x", "period_label": "2026"
    })).json()
    deleted = await api.delete(f"/api/benchmarks/{created['id']}", headers=h)
    assert deleted.status_code == 200
    listed = await api.get("/api/benchmarks", headers=h)
    assert all(b["id"] != created["id"] for b in listed.json())


# --- Service-level lookup logic ---------------------------------------------
@pytest.mark.asyncio
async def test_get_current_prefers_specific_platform_over_cross_platform(async_session_factory):
    import uuid
    async with async_session_factory() as s:
        user_id = uuid.uuid4()
        await benchmark_service.create(s, {
            "industry_category": "real_estate", "platform": "all", "metric": "engagement_rate",
            "value": 0.015, "source": "x", "period_label": "2026",
        }, updated_by_user_id=user_id)
        await benchmark_service.create(s, {
            "industry_category": "real_estate", "platform": "instagram", "metric": "engagement_rate",
            "value": 0.021, "source": "x", "period_label": "2026",
        }, updated_by_user_id=user_id)

        specific = await benchmark_service.get_current(
            s, industry_category="real_estate", platform="instagram")
        assert specific.value == 0.021

        fallback = await benchmark_service.get_current(
            s, industry_category="real_estate", platform="tiktok")   # no tiktok figure
        assert fallback.value == 0.015   # falls back to "all"


@pytest.mark.asyncio
async def test_get_current_returns_none_when_nothing_matches(async_session_factory):
    async with async_session_factory() as s:
        result = await benchmark_service.get_current(s, industry_category="finance", platform="youtube")
    assert result is None


@pytest.mark.asyncio
async def test_get_current_prefers_most_recently_updated(async_session_factory):
    import uuid
    async with async_session_factory() as s:
        user_id = uuid.uuid4()
        await benchmark_service.create(s, {
            "industry_category": "creators", "platform": "all", "value": 0.01,
            "source": "old report", "period_label": "2025",
        }, updated_by_user_id=user_id)
        await benchmark_service.create(s, {
            "industry_category": "creators", "platform": "all", "value": 0.03,
            "source": "new report", "period_label": "2026",
        }, updated_by_user_id=user_id)

        current = await benchmark_service.get_current(s, industry_category="creators")
        assert current.value == 0.03
        assert current.source == "new report"
