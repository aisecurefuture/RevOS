"""Optional integrations: status, exports, inbound + Stripe webhooks (Module 13)."""

from __future__ import annotations

import hashlib
import hmac
import json
import time

import pytest
from app.config import settings
from app.models.user import Role


async def _login(api, email, password):
    r = await api.post("/api/auth/login", json={"email": email, "password": password})
    assert r.status_code == 200, r.text
    return {"X-CSRF-Token": r.json()["csrf_token"]}


@pytest.mark.asyncio
async def test_status_reports_unconfigured(api, make_user):
    await _login(api, **await make_user("admin@test.com", "AdminPass123", Role.admin))
    status = (await api.get("/api/integrations/status")).json()
    assert status["stripe"] is False
    assert status["email_live"] is False
    assert "analytics" in status and "social" in status


@pytest.mark.asyncio
async def test_status_requires_admin(api, make_user):
    h = await _login(api, **await make_user("ed@test.com", "EditorPass123", Role.editor))
    assert (await api.get("/api/integrations/status", headers=h)).status_code == 403


@pytest.mark.asyncio
async def test_contact_export_csv_and_notion(api, make_user):
    h = await _login(api, **await make_user("admin@test.com", "AdminPass123", Role.admin))
    await api.post("/api/contacts", headers=h,
                   json={"first_name": "Ada", "email": "ada@x.com", "title": "CTO"})

    csv_resp = await api.get("/api/integrations/export?entity=contacts&fmt=csv")
    assert csv_resp.status_code == 200
    assert "ada@x.com" in csv_resp.text

    notion = await api.get("/api/integrations/export?entity=contacts&fmt=notion")
    assert notion.status_code == 200
    assert notion.headers["content-type"].startswith("text/markdown")
    assert "| First | Last |" in notion.text  # markdown table header


@pytest.mark.asyncio
async def test_zapier_inbound_creates_contact_not_lead(api, make_user, monkeypatch):
    monkeypatch.setattr(settings, "zapier_webhook_secret", "zap-secret")
    h = await _login(api, **await make_user("admin@test.com", "AdminPass123", Role.admin))
    bid = (await api.post("/api/brands", headers=h, json={"name": "Zap Brand"})).json()["id"]

    body = json.dumps({"brand_id": bid, "email": "zap@x.com", "first_name": "Zee"}).encode()
    ts = str(int(time.time()))
    sig = hmac.new(b"zap-secret", f"{ts}.".encode() + body, hashlib.sha256).hexdigest()

    ok = await api.post("/api/integrations/inbound/contact", content=body,
                        headers={"X-Signature": sig, "X-Timestamp": ts,
                                 "content-type": "application/json"})
    assert ok.status_code == 200

    # Wrong signature -> rejected.
    bad = await api.post("/api/integrations/inbound/contact", content=body,
                         headers={"X-Signature": "wrong", "X-Timestamp": ts,
                                  "content-type": "application/json"})
    assert bad.status_code == 401

    # Stale timestamp -> rejected (replay protection).
    old_ts = str(int(time.time()) - 3600)
    old_sig = hmac.new(b"zap-secret", f"{old_ts}.".encode() + body, hashlib.sha256).hexdigest()
    stale = await api.post("/api/integrations/inbound/contact", content=body,
                           headers={"X-Signature": old_sig, "X-Timestamp": old_ts,
                                    "content-type": "application/json"})
    assert stale.status_code == 401

    # Created as a contact; never a mailable lead.
    assert any(c["email"] == "zap@x.com" for c in (await api.get("/api/contacts")).json())
    assert (await api.get("/api/leads")).json() == []


@pytest.mark.asyncio
async def test_stripe_webhook_records_revenue(api, make_user, monkeypatch):
    monkeypatch.setattr(settings, "stripe_webhook_secret", "whsec_stripe")
    h = await _login(api, **await make_user("admin@test.com", "AdminPass123", Role.admin))
    bid = (await api.post("/api/brands", headers=h, json={"name": "Pay Brand"})).json()["id"]

    event = {"type": "checkout.session.completed",
             "data": {"object": {"id": "cs_1", "amount_total": 4900, "currency": "usd",
                                  "metadata": {"brand_id": bid}}}}
    payload = json.dumps(event).encode()
    ts = str(int(time.time()))
    sig = hmac.new(b"whsec_stripe", f"{ts}.".encode() + payload, hashlib.sha256).hexdigest()

    resp = await api.post("/api/webhooks/stripe", content=payload,
                          headers={"Stripe-Signature": f"t={ts},v1={sig}",
                                   "content-type": "application/json"})
    assert resp.status_code == 200
    assert resp.json()["revenue_recorded"] is True

    overview = (await api.get(f"/api/analytics/overview?brand_id={bid}")).json()
    assert overview["revenue_mtd_cents"] == 4900


@pytest.mark.asyncio
async def test_stripe_webhook_rejects_bad_signature(api, make_user, monkeypatch):
    monkeypatch.setattr(settings, "stripe_webhook_secret", "whsec_stripe")
    await _login(api, **await make_user("admin@test.com", "AdminPass123", Role.admin))
    resp = await api.post("/api/webhooks/stripe", content=b"{}",
                          headers={"Stripe-Signature": "t=1,v1=bad"})
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_checkout_link_from_payment_link(api, make_user):
    h = await _login(api, **await make_user("admin@test.com", "AdminPass123", Role.admin))
    bid = (await api.post("/api/brands", headers=h, json={"name": "Shop"})).json()["id"]
    offer = (await api.post("/api/offers", headers=h, json={
        "brand_id": bid, "name": "Book", "offer_type": "book",
        "stripe_payment_link": "https://buy.stripe.com/test_123"})).json()
    link = await api.get(f"/api/integrations/checkout/{offer['id']}")
    assert link.status_code == 200
    assert link.json()["url"] == "https://buy.stripe.com/test_123"
