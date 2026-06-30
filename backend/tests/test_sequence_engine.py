"""Email sequence engine: enroll, tick, delays, goals, A/B, approval (Module 8)."""

from __future__ import annotations

import pytest
from app.models.email import EmailMessage
from app.models.lead import ConsentStatus, Lead
from app.models.user import Role
from sqlmodel import select


async def _login(api, email, password):
    r = await api.post("/api/auth/login", json={"email": email, "password": password})
    assert r.status_code == 200, r.text
    return {"X-CSRF-Token": r.json()["csrf_token"]}


async def _confirmed_lead(api, headers, brand_id, email="lead@x.com") -> str:
    form = (await api.post("/api/forms", headers=headers, json={
        "brand_id": brand_id, "name": "L", "double_optin": False})).json()
    await api.post(f"/api/public/forms/{form['slug']}/submit",
                   json={"email": email, "first_name": "Sam", "consent": True})
    leads = (await api.get(f"/api/leads?search={email}")).json()
    return leads[0]["id"]


async def _sequence_with_steps(api, headers, brand_id, steps, **seq):
    body = {"brand_id": brand_id, "name": "Seq", **seq}
    sid = (await api.post("/api/sequences", headers=headers, json=body)).json()["id"]
    for i, step in enumerate(steps):
        await api.post(f"/api/sequences/{sid}/steps", headers=headers,
                       json={"order_index": i, "delay_minutes": 0, **step})
    await api.post(f"/api/sequences/{sid}/activate", headers=headers)
    return sid


async def _count_sequence_emails(factory, status="sent") -> int:
    async with factory() as s:
        rows = (await s.execute(
            select(EmailMessage).where(EmailMessage.category == "sequence")
        )).scalars().all()
        return sum(1 for m in rows if m.status == status)


@pytest.mark.asyncio
async def test_two_step_sequence_runs_to_completion(api, make_user, async_session_factory):
    h = await _login(api, **await make_user("admin@test.com", "AdminPass123", Role.admin))
    bid = (await api.post("/api/brands", headers=h, json={"name": "Seq Brand"})).json()["id"]
    lead_id = await _confirmed_lead(api, h, bid)
    sid = await _sequence_with_steps(api, h, bid, [
        {"name": "One", "subject": "Hi {{first_name}}", "html_body": "<p>1</p>"},
        {"name": "Two", "subject": "Two", "html_body": "<p>2</p>"},
    ])

    enr = await api.post(f"/api/sequences/{sid}/enroll", headers=h, json={"lead_id": lead_id})
    assert enr.status_code == 201

    t1 = (await api.post("/api/sequences/tick", headers=h)).json()
    assert t1["sent"] == 1
    t2 = (await api.post("/api/sequences/tick", headers=h)).json()
    assert t2["sent"] == 1 and t2["completed"] == 1
    assert await _count_sequence_emails(async_session_factory) == 2

    enrollments = (await api.get(f"/api/sequences/{sid}/enrollments")).json()
    assert enrollments[0]["status"] == "completed"


@pytest.mark.asyncio
async def test_future_delay_not_due(api, make_user, async_session_factory):
    h = await _login(api, **await make_user("admin@test.com", "AdminPass123", Role.admin))
    bid = (await api.post("/api/brands", headers=h, json={"name": "B"})).json()["id"]
    lead_id = await _confirmed_lead(api, h, bid)
    sid = await _sequence_with_steps(api, h, bid, [{"name": "Later", "subject": "x",
                                                    "html_body": "<p>x</p>"}])
    # Override the first step's delay to far future after activation.
    steps = (await api.get(f"/api/sequences/{sid}")).json()["steps"]
    await api.patch(f"/api/sequences/steps/{steps[0]['id']}", headers=h,
                    json={"delay_minutes": 100000})
    await api.post(f"/api/sequences/{sid}/enroll", headers=h, json={"lead_id": lead_id})
    tick = (await api.post("/api/sequences/tick", headers=h)).json()
    assert tick["sent"] == 0


@pytest.mark.asyncio
async def test_unsubscribed_lead_stops_sequence(api, make_user, async_session_factory):
    h = await _login(api, **await make_user("admin@test.com", "AdminPass123", Role.admin))
    bid = (await api.post("/api/brands", headers=h, json={"name": "B"})).json()["id"]
    lead_id = await _confirmed_lead(api, h, bid)
    sid = await _sequence_with_steps(api, h, bid, [{"name": "One", "subject": "x",
                                                    "html_body": "<p>x</p>"}])
    await api.post(f"/api/sequences/{sid}/enroll", headers=h, json={"lead_id": lead_id})

    async with async_session_factory() as s:
        lead = await s.get(Lead, __import__("uuid").UUID(lead_id))
        lead.consent_status = ConsentStatus.unsubscribed
        s.add(lead)
        await s.commit()

    tick = (await api.post("/api/sequences/tick", headers=h)).json()
    assert tick["sent"] == 0 and tick["stopped"] == 1


@pytest.mark.asyncio
async def test_goal_event_stops_sequence(api, make_user, async_session_factory):
    h = await _login(api, **await make_user("admin@test.com", "AdminPass123", Role.admin))
    bid = (await api.post("/api/brands", headers=h, json={"name": "B"})).json()["id"]
    lead_id = await _confirmed_lead(api, h, bid)
    sid = await _sequence_with_steps(api, h, bid,
                                     [{"name": "One", "subject": "x", "html_body": "<p>x</p>"}],
                                     goal_event="purchased", stop_on_goal=True)
    await api.post(f"/api/sequences/{sid}/enroll", headers=h, json={"lead_id": lead_id})

    goal = await api.post("/api/sequences/goal", headers=h,
                          json={"lead_id": lead_id, "event_name": "purchased"})
    assert goal.status_code == 200
    enrollments = (await api.get(f"/api/sequences/{sid}/enrollments")).json()
    assert enrollments[0]["status"] == "goal_met"


@pytest.mark.asyncio
async def test_ab_subject_variant_used(api, make_user, async_session_factory):
    h = await _login(api, **await make_user("admin@test.com", "AdminPass123", Role.admin))
    bid = (await api.post("/api/brands", headers=h, json={"name": "B"})).json()["id"]
    lead_id = await _confirmed_lead(api, h, bid)
    sid = await _sequence_with_steps(api, h, bid, [{
        "name": "AB", "html_body": "<p>x</p>",
        "ab_variants": [{"label": "A", "subject": "AAA"}, {"label": "B", "subject": "BBB"}],
    }])
    await api.post(f"/api/sequences/{sid}/enroll", headers=h, json={"lead_id": lead_id})
    await api.post("/api/sequences/tick", headers=h)

    async with async_session_factory() as s:
        msg = (await s.execute(
            select(EmailMessage).where(EmailMessage.category == "sequence")
        )).scalars().first()
        assert msg.subject in {"AAA", "BBB"}
        assert msg.variant_label in {"A", "B"}


@pytest.mark.asyncio
async def test_per_step_approval_gate(api, make_user, async_session_factory):
    h = await _login(api, **await make_user("admin@test.com", "AdminPass123", Role.admin))
    bid = (await api.post("/api/brands", headers=h, json={"name": "B"})).json()["id"]
    lead_id = await _confirmed_lead(api, h, bid)
    sid = await _sequence_with_steps(api, h, bid, [{
        "name": "Gated", "subject": "x", "html_body": "<p>x</p>", "require_approval": True}])
    await api.post(f"/api/sequences/{sid}/enroll", headers=h, json={"lead_id": lead_id})

    tick = (await api.post("/api/sequences/tick", headers=h)).json()
    assert tick["awaiting_approval"] == 1 and tick["sent"] == 0
    assert await _count_sequence_emails(async_session_factory) == 0

    approvals = (await api.get("/api/approvals")).json()
    step_approval = next(a for a in approvals if a["action_type"] == "sequence_step_send")
    res = await api.post(f"/api/approvals/{step_approval['id']}/approve", headers=h)
    assert res.json()["sent"] == 1
    assert await _count_sequence_emails(async_session_factory) == 1


@pytest.mark.asyncio
async def test_paused_sequence_skips_then_resumes(api, make_user, async_session_factory):
    h = await _login(api, **await make_user("admin@test.com", "AdminPass123", Role.admin))
    bid = (await api.post("/api/brands", headers=h, json={"name": "B"})).json()["id"]
    lead_id = await _confirmed_lead(api, h, bid)
    sid = await _sequence_with_steps(api, h, bid, [{"name": "One", "subject": "x",
                                                    "html_body": "<p>x</p>"}])
    await api.post(f"/api/sequences/{sid}/enroll", headers=h, json={"lead_id": lead_id})

    await api.post(f"/api/sequences/{sid}/pause", headers=h)
    assert (await api.post("/api/sequences/tick", headers=h)).json()["sent"] == 0

    await api.post(f"/api/sequences/{sid}/activate", headers=h)
    assert (await api.post("/api/sequences/tick", headers=h)).json()["sent"] == 1


@pytest.mark.asyncio
async def test_duplicate_enroll_blocked(api, make_user):
    h = await _login(api, **await make_user("admin@test.com", "AdminPass123", Role.admin))
    bid = (await api.post("/api/brands", headers=h, json={"name": "B"})).json()["id"]
    lead_id = await _confirmed_lead(api, h, bid)
    sid = await _sequence_with_steps(api, h, bid, [{"name": "One", "subject": "x",
                                                    "html_body": "<p>x</p>"}])
    first = await api.post(f"/api/sequences/{sid}/enroll", headers=h, json={"lead_id": lead_id})
    assert first.status_code == 201
    second = await api.post(f"/api/sequences/{sid}/enroll", headers=h, json={"lead_id": lead_id})
    assert second.status_code == 400


@pytest.mark.asyncio
async def test_form_auto_enrolls_on_confirm(api, make_user):
    h = await _login(api, **await make_user("admin@test.com", "AdminPass123", Role.admin))
    bid = (await api.post("/api/brands", headers=h, json={"name": "B"})).json()["id"]
    sid = await _sequence_with_steps(api, h, bid, [{"name": "One", "subject": "x",
                                                    "html_body": "<p>x</p>"}])
    form = (await api.post("/api/forms", headers=h, json={
        "brand_id": bid, "name": "Enroller", "double_optin": False,
        "enroll_sequence_id": sid})).json()
    await api.post(f"/api/public/forms/{form['slug']}/submit",
                   json={"email": "auto@x.com", "consent": True})

    enrollments = (await api.get(f"/api/sequences/{sid}/enrollments")).json()
    assert len(enrollments) == 1


@pytest.mark.asyncio
async def test_tick_requires_admin(api, make_user):
    h = await _login(api, **await make_user("ed@test.com", "EditorPass123", Role.editor))
    assert (await api.post("/api/sequences/tick", headers=h)).status_code == 403
