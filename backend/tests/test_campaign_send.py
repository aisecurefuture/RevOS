"""Bulk campaign send: approval-first gate, dispatch, reject (Module 7)."""

from __future__ import annotations

import pytest
from app.models.user import Role


async def _login(api, email, password):
    r = await api.post("/api/auth/login", json={"email": email, "password": password})
    assert r.status_code == 200, r.text
    return {"X-CSRF-Token": r.json()["csrf_token"]}


async def _setup_with_confirmed_leads(api, make_user, emails=("a@x.com", "b@x.com")):
    h = await _login(api, **await make_user("admin@test.com", "AdminPass123", Role.admin))
    bid = (await api.post("/api/brands", headers=h, json={"name": "Send Brand"})).json()["id"]
    form = (await api.post("/api/forms", headers=h, json={
        "brand_id": bid, "name": "List", "double_optin": False})).json()
    for e in emails:
        await api.post(f"/api/public/forms/{form['slug']}/submit",
                       json={"email": e, "consent": True})
    cid = (await api.post("/api/campaigns", headers=h,
                          json={"brand_id": bid, "name": "Promo"})).json()["id"]
    return h, bid, cid


@pytest.mark.asyncio
async def test_campaign_requires_approval_before_send(api, make_user):
    h, _bid, cid = await _setup_with_confirmed_leads(api, make_user)

    prep = await api.post(f"/api/campaigns/{cid}/email/prepare", headers=h, json={
        "subject": "Hi {{first_name}}", "html_body": "<p>Hello {{first_name}}</p>"})
    assert prep.status_code == 200
    assert prep.json()["recipient_count"] == 2
    approval_id = prep.json()["approval_id"]

    # Before approval: messages exist but are NOT sent.
    msgs = (await api.get(f"/api/emails?campaign_id={cid}")).json()
    assert len(msgs) == 2
    assert all(m["status"] == "pending_approval" for m in msgs)

    # The request shows up in the pending approval queue.
    pending = (await api.get("/api/approvals")).json()
    assert any(a["id"] == approval_id for a in pending)

    # Approve -> dispatched.
    approve = await api.post(f"/api/approvals/{approval_id}/approve", headers=h)
    assert approve.status_code == 200
    assert approve.json()["sent"] == 2
    msgs = (await api.get(f"/api/emails?campaign_id={cid}")).json()
    assert all(m["status"] == "sent" for m in msgs)


@pytest.mark.asyncio
async def test_campaign_reject_cancels_messages(api, make_user):
    h, _bid, cid = await _setup_with_confirmed_leads(api, make_user)
    prep = await api.post(f"/api/campaigns/{cid}/email/prepare", headers=h, json={
        "subject": "x", "html_body": "<p>x</p>"})
    approval_id = prep.json()["approval_id"]

    rej = await api.post(f"/api/approvals/{approval_id}/reject", headers=h,
                         json={"reason": "wrong copy"})
    assert rej.status_code == 200
    msgs = (await api.get(f"/api/emails?campaign_id={cid}")).json()
    assert all(m["status"] == "failed" for m in msgs)


@pytest.mark.asyncio
async def test_no_cold_spam_without_confirmed_recipients(api, make_user):
    h = await _login(api, **await make_user("admin@test.com", "AdminPass123", Role.admin))
    bid = (await api.post("/api/brands", headers=h, json={"name": "Empty"})).json()["id"]
    cid = (await api.post("/api/campaigns", headers=h,
                          json={"brand_id": bid, "name": "Promo"})).json()["id"]
    prep = await api.post(f"/api/campaigns/{cid}/email/prepare", headers=h, json={
        "subject": "x", "html_body": "<p>x</p>"})
    assert prep.status_code == 400  # no confirmed, mailable recipients


@pytest.mark.asyncio
async def test_prepare_requires_admin(api, make_user):
    # Build the campaign as admin, then an editor must not be able to prepare a send.
    h, _bid, cid = await _setup_with_confirmed_leads(api, make_user)
    editor_h = await _login(api, **await make_user("ed@test.com", "EditorPass123", Role.editor))
    r = await api.post(f"/api/campaigns/{cid}/email/prepare", headers=editor_h, json={
        "subject": "x", "html_body": "<p>x</p>"})
    assert r.status_code == 403
