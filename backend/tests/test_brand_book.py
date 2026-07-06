"""Brand Book — grounding + the hallucination/compliance gate (P3-M1).

The numeric-claim heuristic and the content gate are the load-bearing pieces:
an ungrounded statistic is the signature of a hallucination, and banned terms
must hard-block.
"""

from __future__ import annotations

import pytest

from app.services import brand_book_service as svc


# ---------------------------------------------------------------------------
# Numeric-claim extraction (pure)
# ---------------------------------------------------------------------------

def test_extract_claim_numbers_catches_stats_ignores_noise():
    got = svc._extract_claim_numbers(
        "We serve 10,000 customers with 99.9% uptime and 3x ROI, since 2018. Read 5 tips."
    )
    assert (10000.0, "") in got
    assert (99.9, "%") in got
    assert (3.0, "x") in got
    assert not any(t == "" and v == 5 for v, t in got)      # "5 tips" ignored
    assert not any(v == 2018 for v, _ in got)               # year ignored


def test_extract_claim_numbers_money_and_multipliers():
    got = svc._extract_claim_numbers("Raised $2M and reached 1 million users, up 50%.")
    assert (2_000_000.0, "$") in got
    assert (1_000_000.0, "") in got
    assert (50.0, "%") in got


# ---------------------------------------------------------------------------
# API setup helpers
# ---------------------------------------------------------------------------

async def _register_owner(api, email="owner@test.com"):
    r = await api.post("/api/auth/register", json={
        "email": email, "password": "OwnerPass123", "full_name": "Owner",
    })
    assert r.status_code == 201, r.text
    return {"X-CSRF-Token": r.json()["csrf_token"]}


async def _brand(api, headers):
    return (await api.post("/api/brands", headers=headers, json={"name": "Acme"})).json()["id"]


# ---------------------------------------------------------------------------
# Content check via the API (the gate)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_check_flags_ungrounded_numbers_and_passes_grounded(api):
    h = await _register_owner(api)
    bid = await _brand(api, h)

    # One approved proof point mentioning 10,000.
    await api.post(f"/api/brand-book/{bid}/claims", headers=h, json={
        "claim": "Trusted by 10,000 teams", "category": "metric",
    })

    # A grounded number passes; an invented one is flagged.
    r = (await api.post(f"/api/brand-book/{bid}/check", headers=h, json={
        "text": "Trusted by 10,000 teams with 99.9% uptime.",
    })).json()
    assert r["blocked"] is False
    assert "99.9%" in r["unverified_numbers"]
    assert r["passed"] is False

    clean = (await api.post(f"/api/brand-book/{bid}/check", headers=h, json={
        "text": "We're trusted by 10,000 teams.",
    })).json()
    assert clean["unverified_numbers"] == []
    assert clean["passed"] is True


@pytest.mark.asyncio
async def test_unapproved_claim_does_not_ground(api):
    h = await _register_owner(api)
    bid = await _brand(api, h)
    await api.post(f"/api/brand-book/{bid}/claims", headers=h, json={
        "claim": "88888 downloads", "category": "metric", "approved": False,
    })
    r = (await api.post(f"/api/brand-book/{bid}/check", headers=h, json={
        "text": "We hit 88888 downloads.",
    })).json()
    assert "88888" in r["unverified_numbers"]  # unapproved → not a valid grounding


@pytest.mark.asyncio
async def test_banned_term_hard_blocks(api):
    h = await _register_owner(api)
    bid = await _brand(api, h)
    await api.patch(f"/api/brand-book/{bid}", headers=h, json={"banned_terms": ["guarantee"]})

    r = (await api.post(f"/api/brand-book/{bid}/check", headers=h, json={
        "text": "We guarantee results.",
    })).json()
    assert r["blocked"] is True
    assert "guarantee" in r["banned_hits"]
    assert r["passed"] is False


@pytest.mark.asyncio
async def test_required_disclaimer_flagged_when_missing(api):
    h = await _register_owner(api)
    bid = await _brand(api, h)
    await api.patch(f"/api/brand-book/{bid}", headers=h, json={
        "required_disclaimers": ["Results not typical"],
    })
    missing = (await api.post(f"/api/brand-book/{bid}/check", headers=h, json={
        "text": "Amazing results await.", "require_disclaimers": True,
    })).json()
    assert "Results not typical" in missing["missing_disclaimers"]

    present = (await api.post(f"/api/brand-book/{bid}/check", headers=h, json={
        "text": "Amazing results await. Results not typical.", "require_disclaimers": True,
    })).json()
    assert present["missing_disclaimers"] == []


# ---------------------------------------------------------------------------
# Grounding assembly
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_grounding_context_includes_book_and_claims(api):
    h = await _register_owner(api)
    bid = await _brand(api, h)
    await api.patch(f"/api/brand-book/{bid}", headers=h, json={
        "mission": "Make security effortless.",
        "key_messages": ["Fast to deploy", "Loved by teams"],
        "compliance_notes": "Never promise specific breach prevention.",
        "is_published": True,
    })
    await api.post(f"/api/brand-book/{bid}/claims", headers=h, json={
        "claim": "SOC 2 Type II certified", "category": "certification",
    })

    g = (await api.get(f"/api/brand-book/{bid}/grounding", headers=h)).json()
    ctx = g["prompt_context"]
    assert "Acme" in ctx
    assert "Make security effortless." in ctx
    assert "SOC 2 Type II certified" in ctx
    assert "Approved claims" in ctx
    assert "Never invent statistics" in ctx  # the guardrail instruction
    assert "Never promise specific breach prevention." in ctx
    assert g["is_published"] is True
    assert "SOC 2 Type II certified" in g["approved_claims"]


@pytest.mark.asyncio
async def test_grounding_warns_when_no_claims(api):
    h = await _register_owner(api)
    bid = await _brand(api, h)
    g = (await api.get(f"/api/brand-book/{bid}/grounding", headers=h)).json()
    assert "do NOT state any specific" in g["prompt_context"]
    assert g["approved_claims"] == []


@pytest.mark.asyncio
async def test_narrative_fields_round_trip_and_ground(api):
    """Vision, anti-audience, core values, brand story, archetype, and voice
    spectrum all persist and flow into the grounding prompt context."""
    h = await _register_owner(api)
    bid = await _brand(api, h)
    r = await api.patch(f"/api/brand-book/{bid}", headers=h, json={
        "vision": "A world where every tattoo artist has a thriving, ethical practice.",
        "audience_exclusions": "Artists with harassment allegations.",
        "core_values": [
            {"value": "Presence", "statement": "I focus on my next rep.", "example": "Daily gratitude posts."},
        ],
        "brand_story": "This is about a kid who got a bad tattoo from a stranger...",
        "brand_archetype": "caregiver",
        "voice_spectrum": {"humor": 2, "energy": 4, "formality": 5, "convention": 3},
    })
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["brand_archetype"] == "caregiver"
    assert body["core_values"][0]["value"] == "Presence"

    g = (await api.get(f"/api/brand-book/{bid}/grounding", headers=h)).json()
    ctx = g["prompt_context"]
    assert "thriving, ethical practice" in ctx
    assert "Artists with harassment allegations." in ctx
    assert "Presence" in ctx and "Daily gratitude posts." in ctx
    assert "a bad tattoo from a stranger" in ctx
    assert "Brand archetype: caregiver" in ctx
    assert "humor=2/5" in ctx


# ---------------------------------------------------------------------------
# CRUD + permissions + isolation
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_claims_and_facts_crud(api):
    h = await _register_owner(api)
    bid = await _brand(api, h)

    c = await api.post(f"/api/brand-book/{bid}/claims", headers=h, json={"claim": "Founded 2015"})
    assert c.status_code == 201
    cid = c.json()["id"]
    f = await api.post(f"/api/brand-book/{bid}/facts", headers=h, json={
        "topic": "Refund policy", "content": "30-day money-back guarantee window.",
    })
    assert f.status_code == 201
    fid = f.json()["id"]

    assert len((await api.get(f"/api/brand-book/{bid}/claims", headers=h)).json()) == 1
    assert len((await api.get(f"/api/brand-book/{bid}/facts", headers=h)).json()) == 1

    assert (await api.delete(f"/api/brand-book/{bid}/claims/{cid}", headers=h)).status_code == 204
    assert (await api.delete(f"/api/brand-book/{bid}/facts/{fid}", headers=h)).status_code == 204
    assert (await api.get(f"/api/brand-book/{bid}/claims", headers=h)).json() == []


@pytest.mark.asyncio
async def test_viewer_cannot_edit(api, make_user):
    from app.models.user import Role

    h = await _register_owner(api)
    bid = await _brand(api, h)

    async def _login(email, password):
        r = await api.post("/api/auth/login", json={"email": email, "password": password})
        return {"X-CSRF-Token": r.json()["csrf_token"]}

    # A viewer in their OWN account can't edit — and can't even see this brand.
    v = await _login(**await make_user("viewer@test.com", "ViewerPass123", Role.viewer))
    r = await api.patch(f"/api/brand-book/{bid}", headers=v, json={"mission": "hijack"})
    assert r.status_code in (403, 404)  # forbidden by role or invisible cross-account


@pytest.mark.asyncio
async def test_cross_account_brand_is_404(api, make_client):
    h = await _register_owner(api)
    bid = await _brand(api, h)

    other = await make_client()
    r2 = await other.post("/api/auth/register", json={
        "email": "other@test.com", "password": "OwnerPass123", "full_name": "Other",
    })
    oh = {"X-CSRF-Token": r2.json()["csrf_token"]}
    # The other account cannot read or check this brand's book.
    assert (await other.get(f"/api/brand-book/{bid}", headers=oh)).status_code == 404
    assert (await other.post(f"/api/brand-book/{bid}/check", headers=oh,
                             json={"text": "hi"})).status_code == 404
