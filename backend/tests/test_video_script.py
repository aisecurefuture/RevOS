"""Viral video script engine (Phase 3 M4).

The LLM is mocked; the tests pin down the two things that matter: scripts are
sized to the target duration, and every generated/edited script is run through
the brand-book accuracy gate (banned terms block, ungrounded stats flag).
"""

from __future__ import annotations

from unittest.mock import patch

import pytest

from app.services import script_engine_service as svc


def test_word_target_sizes_to_duration():
    assert svc.word_target(15) == 38   # ~150 wpm
    assert svc.word_target(60) == 150
    assert svc.word_target(120) == 300


async def _register_owner(api, email="owner@test.com"):
    r = await api.post("/api/auth/register", json={
        "email": email, "password": "OwnerPass123", "full_name": "Owner",
    })
    assert r.status_code == 201, r.text
    return {"X-CSRF-Token": r.json()["csrf_token"]}


async def _brand_with_book(api, h):
    bid = (await api.post("/api/brands", headers=h, json={"name": "Acme"})).json()["id"]
    await api.post(f"/api/brand-book/{bid}/claims", headers=h, json={
        "claim": "Trusted by 10,000 teams", "category": "metric",
    })
    return bid


def _mock_ai(text: str):
    return patch("app.services.ai_service.generate", return_value=text)


# ---------------------------------------------------------------------------
# Generation + gate
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_generate_clean_script_passes_gate(api):
    h = await _register_owner(api)
    bid = await _brand_with_book(api, h)

    text = ("Ever feel stuck? Here's the one move that changes everything. "
            "Trusted by 10,000 teams. Try it today.")
    with _mock_ai(text):
        r = await api.post("/api/scripts/generate", headers=h, json={
            "brand_id": bid, "target_seconds": 15, "angle": "productivity",
        })
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["passed_gate"] is True
    assert body["gate"]["blocked"] is False
    assert body["hook"] == "Ever feel stuck?"
    assert body["word_count"] == len(text.split())


@pytest.mark.asyncio
async def test_generate_banned_term_is_blocked(api):
    h = await _register_owner(api)
    bid = await _brand_with_book(api, h)
    await api.patch(f"/api/brand-book/{bid}", headers=h, json={"banned_terms": ["guarantee"]})

    with _mock_ai("We guarantee you results. Start now."):
        r = await api.post("/api/scripts/generate", headers=h, json={
            "brand_id": bid, "target_seconds": 15,
        })
    body = r.json()
    assert body["passed_gate"] is False
    assert body["gate"]["blocked"] is True
    assert "guarantee" in body["gate"]["banned_hits"]


@pytest.mark.asyncio
async def test_generate_ungrounded_stat_is_flagged(api):
    h = await _register_owner(api)
    bid = await _brand_with_book(api, h)

    with _mock_ai("We now serve 500000 happy customers. Join them today."):
        r = await api.post("/api/scripts/generate", headers=h, json={
            "brand_id": bid, "target_seconds": 15,
        })
    body = r.json()
    assert body["passed_gate"] is False
    assert body["gate"]["blocked"] is False           # not banned, just unverified
    assert "500000" in body["gate"]["unverified_numbers"]


@pytest.mark.asyncio
async def test_generate_without_ai_returns_503(api):
    h = await _register_owner(api)
    bid = await _brand_with_book(api, h)
    with _mock_ai(None):  # no provider configured
        r = await api.post("/api/scripts/generate", headers=h, json={
            "brand_id": bid, "target_seconds": 15,
        })
    assert r.status_code == 503
    assert r.json()["error"]["code"] == "ai_unavailable"


# ---------------------------------------------------------------------------
# Edit re-runs the gate
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_edit_reruns_gate(api):
    h = await _register_owner(api)
    bid = await _brand_with_book(api, h)
    await api.patch(f"/api/brand-book/{bid}", headers=h, json={"banned_terms": ["miracle"]})

    with _mock_ai("A clean, honest script about our product. Try it."):
        sid = (await api.post("/api/scripts/generate", headers=h, json={
            "brand_id": bid, "target_seconds": 15,
        })).json()["id"]

    # Edit to introduce a banned term → gate must re-run and block.
    edited = await api.patch(f"/api/scripts/{sid}", headers=h, json={
        "script": "This is a miracle cure for your problems.",
    })
    assert edited.status_code == 200
    assert edited.json()["gate"]["blocked"] is True
    assert edited.json()["passed_gate"] is False


# ---------------------------------------------------------------------------
# CRUD + permissions
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_list_get_delete(api):
    h = await _register_owner(api)
    bid = await _brand_with_book(api, h)
    with _mock_ai("Short clean script. Go."):
        sid = (await api.post("/api/scripts/generate", headers=h, json={
            "brand_id": bid, "target_seconds": 7,
        })).json()["id"]

    assert len((await api.get("/api/scripts", headers=h)).json()) == 1
    assert (await api.get(f"/api/scripts/{sid}", headers=h)).status_code == 200
    assert (await api.delete(f"/api/scripts/{sid}", headers=h)).status_code == 204
    assert (await api.get("/api/scripts", headers=h)).json() == []


@pytest.mark.asyncio
async def test_viewer_cannot_generate(api, make_user):
    from app.models.user import Role

    h = await _register_owner(api)
    bid = await _brand_with_book(api, h)

    v = await api.post("/api/auth/login", json={
        "email": (await make_user("v@test.com", "ViewerPass123", Role.viewer))["email"],
        "password": "ViewerPass123",
    })
    vh = {"X-CSRF-Token": v.json()["csrf_token"]}
    with _mock_ai("x"):
        r = await api.post("/api/scripts/generate", headers=vh, json={
            "brand_id": bid, "target_seconds": 15,
        })
    assert r.status_code == 403
