"""M5 — LLM claim verification layered on the deterministic gate (Phase 3).

The verifier itself uses an LLM, so the load-bearing property is that it FAILS
CLOSED: if it can't run or parse, content is never treated as passed. These
tests pin that down, plus the robust JSON parsing and the layering with the
deterministic gate.
"""

from __future__ import annotations

import uuid

import pytest

from app.services import ai_service
from app.services import brand_book_service as bb


# ---------------------------------------------------------------------------
# Verdict parsing (tolerant, fail-closed)
# ---------------------------------------------------------------------------

def test_parse_verdict_variants():
    assert bb._parse_verdict('{"unsupported_claims": ["a", "b"]}') == ["a", "b"]
    assert bb._parse_verdict('```json\n{"unsupported_claims": []}\n```') == []
    assert bb._parse_verdict('Sure! {"unsupported_claims": ["x"]} — done.') == ["x"]
    assert bb._parse_verdict("no json here") is None
    assert bb._parse_verdict('{"wrong_key": 1}') is None
    assert bb._parse_verdict('{"unsupported_claims": "not a list"}') is None


# ---------------------------------------------------------------------------
# verify_claims_llm
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_verify_claims_no_provider(monkeypatch):
    monkeypatch.setattr(ai_service, "ai_available", lambda: False)
    r = await bb.verify_claims_llm(approved=[], facts=[], content="x")
    assert r.ok is False and r.error == "no_provider"


@pytest.mark.asyncio
async def test_verify_claims_clean(monkeypatch):
    monkeypatch.setattr(ai_service, "ai_available", lambda: True)
    monkeypatch.setattr(ai_service, "analyze", lambda **kw: '{"unsupported_claims": []}')
    r = await bb.verify_claims_llm(approved=["Trusted by 10,000 teams"], facts=[], content="Trusted by 10,000 teams.")
    assert r.ok is True and r.unsupported_claims == []


@pytest.mark.asyncio
async def test_verify_claims_flags_unsupported(monkeypatch):
    monkeypatch.setattr(ai_service, "ai_available", lambda: True)
    monkeypatch.setattr(ai_service, "analyze", lambda **kw: '{"unsupported_claims": ["We are FDA approved"]}')
    r = await bb.verify_claims_llm(approved=[], facts=[], content="We are FDA approved.")
    assert r.ok is True and r.unsupported_claims == ["We are FDA approved"]


@pytest.mark.asyncio
async def test_verify_claims_fails_closed_on_call_failure(monkeypatch):
    monkeypatch.setattr(ai_service, "ai_available", lambda: True)
    monkeypatch.setattr(ai_service, "analyze", lambda **kw: None)
    r = await bb.verify_claims_llm(approved=[], facts=[], content="x")
    assert r.ok is False and r.error == "generation_failed"


@pytest.mark.asyncio
async def test_verify_claims_fails_closed_on_unparseable(monkeypatch):
    monkeypatch.setattr(ai_service, "ai_available", lambda: True)
    monkeypatch.setattr(ai_service, "analyze", lambda **kw: "the model rambled, no json")
    r = await bb.verify_claims_llm(approved=[], facts=[], content="x")
    assert r.ok is False and r.error == "unparseable"


# ---------------------------------------------------------------------------
# verify_content — the combined gate
# ---------------------------------------------------------------------------

async def _brand(api):
    r = await api.post("/api/auth/register", json={
        "email": "owner@test.com", "password": "OwnerPass123", "full_name": "O",
    })
    h = {"X-CSRF-Token": r.json()["csrf_token"]}
    bid = (await api.post("/api/brands", headers=h, json={"name": "Acme"})).json()["id"]
    await api.post(f"/api/brand-book/{bid}/claims", headers=h, json={
        "claim": "Trusted by 10,000 teams", "category": "metric",
    })
    return uuid.UUID(bid)


@pytest.mark.asyncio
async def test_verify_content_deterministic_only_when_disabled(api, async_session_factory):
    bid = await _brand(api)
    async with async_session_factory() as s:
        r = await bb.verify_content(s, bid, "Trusted by 10,000 teams.", use_llm=False)
    assert r.llm_checked is False and r.passed is True


@pytest.mark.asyncio
async def test_verify_content_flags_llm_unsupported(api, async_session_factory, monkeypatch):
    bid = await _brand(api)
    monkeypatch.setattr(ai_service, "ai_available", lambda: True)
    monkeypatch.setattr(ai_service, "analyze", lambda **kw: '{"unsupported_claims": ["We are FDA approved"]}')
    async with async_session_factory() as s:
        r = await bb.verify_content(s, bid, "We are FDA approved. Trusted by 10,000 teams.", use_llm=True)
    assert r.llm_checked is True
    assert r.passed is False
    assert "We are FDA approved" in r.unsupported_claims


@pytest.mark.asyncio
async def test_verify_content_fails_closed_when_verifier_errors(api, async_session_factory, monkeypatch):
    """Deterministically-clean content must NOT pass if the LLM verifier
    couldn't run — a false 'clean' is the dangerous failure mode."""
    bid = await _brand(api)
    monkeypatch.setattr(ai_service, "ai_available", lambda: True)
    monkeypatch.setattr(ai_service, "analyze", lambda **kw: None)  # verifier failed
    async with async_session_factory() as s:
        r = await bb.verify_content(s, bid, "Trusted by 10,000 teams.", use_llm=True)
    assert r.deterministic.passed is True   # deterministic layer was clean
    assert r.passed is False                # but the combined verdict fails closed
    assert r.llm_checked is False
    assert r.llm_error == "generation_failed"


@pytest.mark.asyncio
async def test_verify_content_degrades_without_provider(api, async_session_factory, monkeypatch):
    """No AI provider at all → deterministic-only (there's no LLM to verify with,
    and none generated the content), NOT a hard fail."""
    bid = await _brand(api)
    monkeypatch.setattr(ai_service, "ai_available", lambda: False)
    async with async_session_factory() as s:
        r = await bb.verify_content(s, bid, "Trusted by 10,000 teams.", use_llm=True)
    assert r.llm_checked is False and r.passed is True


@pytest.mark.asyncio
async def test_verify_content_clean_passes_both_layers(api, async_session_factory, monkeypatch):
    bid = await _brand(api)
    monkeypatch.setattr(ai_service, "ai_available", lambda: True)
    monkeypatch.setattr(ai_service, "analyze", lambda **kw: '{"unsupported_claims": []}')
    async with async_session_factory() as s:
        r = await bb.verify_content(s, bid, "Trusted by 10,000 teams. Try it.", use_llm=True)
    assert r.llm_checked is True and r.passed is True


# ---------------------------------------------------------------------------
# Script engine picks up the LLM layer when enabled
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_script_engine_applies_llm_verification(api, monkeypatch):
    from app.config import settings as app_settings
    monkeypatch.setattr(app_settings, "llm_claim_verification", True)
    monkeypatch.setattr(ai_service, "ai_available", lambda: True)
    # Script writer returns a script that is deterministically clean...
    monkeypatch.setattr(ai_service, "generate",
                        lambda **kw: "Our platform is FDA approved. Trusted by 10,000 teams. Try it.")
    # ...but the LLM verifier flags an unsupported claim in it.
    monkeypatch.setattr(ai_service, "analyze",
                        lambda **kw: '{"unsupported_claims": ["Our platform is FDA approved"]}')

    r = await api.post("/api/auth/register", json={
        "email": "o@test.com", "password": "OwnerPass123", "full_name": "O",
    })
    h = {"X-CSRF-Token": r.json()["csrf_token"]}
    bid = (await api.post("/api/brands", headers=h, json={"name": "Acme"})).json()["id"]
    await api.post(f"/api/brand-book/{bid}/claims", headers=h, json={
        "claim": "Trusted by 10,000 teams", "category": "metric",
    })

    gen = await api.post("/api/scripts/generate", headers=h, json={
        "brand_id": bid, "target_seconds": 15,
    })
    body = gen.json()
    assert body["passed_gate"] is False
    assert body["gate"]["llm_checked"] is True
    assert "Our platform is FDA approved" in body["gate"]["unsupported_claims"]
