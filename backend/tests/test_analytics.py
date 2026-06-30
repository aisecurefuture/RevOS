"""Analytics, revenue, UTM, and event tracking (Module 12)."""

from __future__ import annotations

import pytest
from app.models.user import Role


async def _login(api, email, password):
    r = await api.post("/api/auth/login", json={"email": email, "password": password})
    assert r.status_code == 200, r.text
    return {"X-CSRF-Token": r.json()["csrf_token"]}


async def _setup(api, h):
    bid = (await api.post("/api/brands", headers=h, json={"name": "Analytics Brand"})).json()["id"]
    form = (await api.post("/api/forms", headers=h, json={
        "brand_id": bid, "name": "List", "double_optin": False})).json()
    for e in ("a@x.com", "b@x.com"):
        await api.post(f"/api/public/forms/{form['slug']}/submit",
                       json={"email": e, "consent": True, "utm_source": "newsletter"})
    return bid


@pytest.mark.asyncio
async def test_overview_and_leads_by_source(api, make_user):
    h = await _login(api, **await make_user("admin@test.com", "AdminPass123", Role.admin))
    bid = await _setup(api, h)

    overview = (await api.get(f"/api/analytics/overview?brand_id={bid}")).json()
    assert overview["subscribers"] == 2
    assert overview["new_leads_30d"] == 2
    assert any(s["count"] == 2 for s in overview["leads_by_source"])

    by_source = (await api.get(f"/api/analytics/leads-by-source?brand_id={bid}")).json()
    assert by_source[0]["count"] == 2


@pytest.mark.asyncio
async def test_email_stats(api, make_user):
    h = await _login(api, **await make_user("admin@test.com", "AdminPass123", Role.admin))
    bid = (await api.post("/api/brands", headers=h, json={"name": "E"})).json()["id"]
    await api.post("/api/emails/test", headers=h, json={
        "brand_id": bid, "to_email": "x@y.com", "subject": "Hi", "html_body": "<p>x</p>"})
    stats = (await api.get(f"/api/analytics/email?brand_id={bid}")).json()
    assert stats["sent"] >= 1


@pytest.mark.asyncio
async def test_won_deal_records_revenue(api, make_user):
    h = await _login(api, **await make_user("admin@test.com", "AdminPass123", Role.admin))
    bid = (await api.post("/api/brands", headers=h, json={"name": "Rev"})).json()["id"]
    stages = (await api.get(f"/api/deals/pipeline?brand_id={bid}")).json()
    won = next(s for s in stages if s["is_won"])
    deal = (await api.post("/api/deals", headers=h, json={
        "brand_id": bid, "name": "Big", "amount_cents": 250000})).json()

    await api.post(f"/api/deals/{deal['id']}/move", headers=h,
                   json={"pipeline_stage_id": won["id"]})

    overview = (await api.get(f"/api/analytics/overview?brand_id={bid}")).json()
    assert overview["revenue_mtd_cents"] == 250000
    revenue = (await api.get(f"/api/analytics/revenue?brand_id={bid}")).json()
    assert sum(r["amount_cents"] for r in revenue) == 250000


@pytest.mark.asyncio
async def test_manual_revenue_and_pipeline_and_funnel(api, make_user):
    h = await _login(api, **await make_user("admin@test.com", "AdminPass123", Role.admin))
    bid = await _setup(api, h)
    rec = await api.post("/api/analytics/revenue", headers=h, json={
        "brand_id": bid, "amount_cents": 9900, "source": "manual"})
    assert rec.status_code == 201

    funnel = (await api.get(f"/api/analytics/funnel?brand_id={bid}")).json()
    leads_stage = next(s for s in funnel if s["stage"] == "Leads")
    assert leads_stage["count"] == 2

    pipeline = (await api.get(f"/api/analytics/pipeline?brand_id={bid}")).json()
    assert any(s["stage"] == "New lead" for s in pipeline)


@pytest.mark.asyncio
async def test_utm_link_redirect_and_click_count(api, make_user):
    h = await _login(api, **await make_user("admin@test.com", "AdminPass123", Role.admin))
    bid = (await api.post("/api/brands", headers=h, json={"name": "U"})).json()["id"]
    link = (await api.post("/api/analytics/utm-links", headers=h, json={
        "brand_id": bid, "name": "Promo", "target_url": "https://example.com/landing",
        "utm_source": "newsletter", "utm_campaign": "launch"})).json()
    code = link["short_code"]

    redirect = await api.get(f"/api/public/u/{code}")
    assert redirect.status_code == 307
    assert "utm_source=newsletter" in redirect.headers["location"]

    links = (await api.get(f"/api/analytics/utm-links?brand_id={bid}")).json()
    assert links[0]["click_count"] == 1


@pytest.mark.asyncio
async def test_public_event_track(api, make_user):
    h = await _login(api, **await make_user("admin@test.com", "AdminPass123", Role.admin))
    bid = (await api.post("/api/brands", headers=h, json={"name": "T"})).json()["id"]
    resp = await api.post("/api/public/track",
                          json={"brand_id": bid, "name": "page_view", "properties": {"path": "/"}})
    assert resp.status_code == 200
    assert resp.json()["ok"] is True


@pytest.mark.asyncio
async def test_analytics_export_csv(api, make_user):
    h = await _login(api, **await make_user("admin@test.com", "AdminPass123", Role.admin))
    bid = await _setup(api, h)
    export = await api.get(f"/api/analytics/export?brand_id={bid}")
    assert export.status_code == 200
    assert export.headers["content-type"].startswith("text/csv")
    assert "source" in export.text
