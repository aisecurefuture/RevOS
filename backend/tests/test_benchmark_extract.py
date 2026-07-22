"""Paste-and-parse extraction assist (BM3) — AI-assisted, human-reviewed
before anything saves."""

from __future__ import annotations

import json

import pytest
from app.core.exceptions import RevOSError
from app.services import benchmark_service


def _make_admin(monkeypatch, *emails):
    from app.config import settings as app_settings
    monkeypatch.setattr(app_settings, "platform_admin_emails", ",".join(emails))


async def _register(api, email="admin@test.com", pw="PassWord1234", name="Admin"):
    r = await api.post("/api/auth/register", json={"email": email, "password": pw, "full_name": name})
    assert r.status_code == 201, r.text
    return {"X-CSRF-Token": r.json()["csrf_token"]}


@pytest.mark.asyncio
async def test_extract_parses_valid_rows(monkeypatch):
    from app.services import ai_service

    monkeypatch.setattr(ai_service, "analyze", lambda **kw: json.dumps([
        {"industry_category": "real_estate", "platform": "instagram", "metric": "engagement_rate", "value": 0.021},
        {"industry_category": "creators", "platform": "all", "metric": "engagement_rate", "value": 0.037},
    ]))
    result = benchmark_service.extract_from_text("Real Estate: 2.1% IG. Creators: 3.7% overall.")
    assert len(result["rows"]) == 2
    assert result["rows"][0]["value"] == 0.021
    assert result["unparsed_note"] is None


@pytest.mark.asyncio
async def test_extract_drops_invalid_rows_and_reports_count(monkeypatch):
    from app.services import ai_service

    monkeypatch.setattr(ai_service, "analyze", lambda **kw: json.dumps([
        {"industry_category": "real_estate", "platform": "instagram", "metric": "engagement_rate", "value": 0.021},
        {"industry_category": "not_a_real_category", "platform": "instagram", "value": 0.02},   # bad category
        {"industry_category": "real_estate", "platform": "myspace", "value": 0.02},              # bad platform
        {"industry_category": "real_estate", "platform": "instagram", "value": 2.1},             # % not fraction
        "not even a dict",
    ]))
    result = benchmark_service.extract_from_text("garbled report text")
    assert len(result["rows"]) == 1
    assert "4 row(s)" in result["unparsed_note"]


@pytest.mark.asyncio
async def test_extract_raises_ai_unavailable_when_no_provider(monkeypatch):
    from app.services import ai_service

    monkeypatch.setattr(ai_service, "analyze", lambda **kw: None)
    with pytest.raises(RevOSError) as exc:
        benchmark_service.extract_from_text("some report text")
    assert exc.value.code == "ai_unavailable"


@pytest.mark.asyncio
async def test_extract_handles_non_json_response_gracefully(monkeypatch):
    from app.services import ai_service

    monkeypatch.setattr(ai_service, "analyze", lambda **kw: "I couldn't parse a table from this text.")
    result = benchmark_service.extract_from_text("weird unstructured text")
    assert result["rows"] == []
    assert "valid JSON" in result["unparsed_note"]


# --- HTTP: bulk save after review -------------------------------------------
@pytest.mark.asyncio
async def test_bulk_create_saves_reviewed_rows(api, monkeypatch):
    _make_admin(monkeypatch, "bulk1@test.com")
    h = await _register(api, "bulk1@test.com")
    resp = await api.post("/api/benchmarks/bulk", headers=h, json={
        "source": "Quid 2026 Social Media Industry Benchmark Report",
        "source_url": "https://www.quid.com/knowledge-hub/resource-library/blog/2026-social-media-industry-benchmark-report",
        "period_label": "2026 Annual",
        "rows": [
            {"industry_category": "real_estate", "platform": "instagram", "metric": "engagement_rate", "value": 0.021},
            {"industry_category": "creators", "platform": "all", "metric": "engagement_rate", "value": 0.037},
        ],
    })
    assert resp.status_code == 201, resp.text
    assert resp.json()["created"] == 2
    assert resp.json()["skipped"] == []

    listed = await api.get("/api/benchmarks", headers=h)
    assert len(listed.json()) == 2


@pytest.mark.asyncio
async def test_bulk_create_skips_duplicates_without_failing_the_batch(api, monkeypatch):
    _make_admin(monkeypatch, "bulk2@test.com")
    h = await _register(api, "bulk2@test.com")
    payload = {
        "source": "x", "period_label": "2026",
        "rows": [{"industry_category": "real_estate", "platform": "instagram",
                  "metric": "engagement_rate", "value": 0.02}],
    }
    first = await api.post("/api/benchmarks/bulk", headers=h, json=payload)
    assert first.json()["created"] == 1

    payload["rows"].append({"industry_category": "creators", "platform": "all",
                            "metric": "engagement_rate", "value": 0.03})
    second = await api.post("/api/benchmarks/bulk", headers=h, json=payload)
    assert second.status_code == 201
    assert second.json()["created"] == 1        # only the new one
    assert len(second.json()["skipped"]) == 1    # the duplicate real_estate row


@pytest.mark.asyncio
async def test_extract_endpoint_requires_platform_admin(api):
    h = await _register(api, "nobody@test.com")
    resp = await api.post("/api/benchmarks/extract", headers=h,
                          json={"text": "x", "source": "x", "period_label": "2026"})
    assert resp.status_code == 403
