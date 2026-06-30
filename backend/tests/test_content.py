"""Content engine: state machine, libraries, ideas, calendar (Module 10)."""

from __future__ import annotations

import pytest
from app.models.user import Role


async def _login(api, email, password):
    r = await api.post("/api/auth/login", json={"email": email, "password": password})
    assert r.status_code == 200, r.text
    return {"X-CSRF-Token": r.json()["csrf_token"]}


async def _brand(api, h):
    return (await api.post("/api/brands", headers=h, json={"name": "Content Brand"})).json()["id"]


@pytest.mark.asyncio
async def test_content_state_machine_happy_path(api, make_user):
    h = await _login(api, **await make_user("admin@test.com", "AdminPass123", Role.admin))
    bid = await _brand(api, h)
    item = await api.post("/api/content", headers=h, json={
        "brand_id": bid, "channel": "linkedin", "title": "Post 1", "body": "Hello"})
    assert item.status_code == 201
    cid = item.json()["id"]
    assert item.json()["state"] == "draft"

    assert (await api.post(f"/api/content/{cid}/submit", headers=h)).json()["state"] == "needs_review"
    assert (await api.post(f"/api/content/{cid}/approve", headers=h)).json()["state"] == "approved"
    sched = await api.post(f"/api/content/{cid}/schedule", headers=h,
                           json={"scheduled_at": "2030-01-01T10:00:00Z"})
    assert sched.json()["state"] == "scheduled"
    pub = await api.post(f"/api/content/{cid}/publish", headers=h)
    assert pub.json()["state"] == "published"
    assert pub.json()["published_at"] is not None


@pytest.mark.asyncio
async def test_invalid_transition_rejected(api, make_user):
    h = await _login(api, **await make_user("admin@test.com", "AdminPass123", Role.admin))
    bid = await _brand(api, h)
    cid = (await api.post("/api/content", headers=h,
                          json={"brand_id": bid, "title": "X"})).json()["id"]
    # draft -> published is not a legal transition.
    assert (await api.post(f"/api/content/{cid}/publish", headers=h)).status_code == 400


@pytest.mark.asyncio
async def test_publish_requires_admin(api, make_user):
    admin_h = await _login(api, **await make_user("admin@test.com", "AdminPass123", Role.admin))
    bid = await _brand(api, admin_h)
    cid = (await api.post("/api/content", headers=admin_h,
                          json={"brand_id": bid, "title": "X"})).json()["id"]
    await api.post(f"/api/content/{cid}/approve", headers=admin_h)

    editor_h = await _login(api, **await make_user("ed@test.com", "EditorPass123", Role.editor))
    assert (await api.post(f"/api/content/{cid}/publish", headers=editor_h)).status_code == 403


@pytest.mark.asyncio
async def test_content_approval_requires_admin(api, make_user):
    admin_h = await _login(api, **await make_user("admin@test.com", "AdminPass123", Role.admin))
    bid = await _brand(api, admin_h)
    cid = (await api.post("/api/content", headers=admin_h,
                          json={"brand_id": bid, "title": "X"})).json()["id"]
    await api.post(f"/api/content/{cid}/submit", headers=admin_h)

    editor_h = await _login(api, **await make_user("ed@test.com", "EditorPass123", Role.editor))
    # Editors draft and submit; only admins approve.
    assert (await api.post(f"/api/content/{cid}/approve", headers=editor_h)).status_code == 403


@pytest.mark.asyncio
async def test_libraries_and_ideas(api, make_user):
    h = await _login(api, **await make_user("admin@test.com", "AdminPass123", Role.admin))
    bid = await _brand(api, h)
    assert (await api.post("/api/content-library/pillars", headers=h,
                           json={"brand_id": bid, "name": "Thought Leadership"})).status_code == 201
    assert (await api.post("/api/content-library/hooks", headers=h,
                           json={"text": "Most people get this wrong"})).status_code == 201
    assert (await api.post("/api/content-library/ctas", headers=h,
                           json={"label": "Request a demo"})).status_code == 201
    pillars = await api.get(f"/api/content-library/pillars?brand_id={bid}")
    assert len(pillars.json()) == 1

    ideas = await api.post("/api/content/ideas", headers=h, json={
        "brand_id": bid, "channel": "linkedin", "count": 4, "topic": "AI security"})
    assert ideas.status_code == 200
    body = ideas.json()
    assert len(body["ideas"]) == 4
    assert "AI security" in body["ideas"][0]


@pytest.mark.asyncio
async def test_calendar_and_repurpose(api, make_user):
    h = await _login(api, **await make_user("admin@test.com", "AdminPass123", Role.admin))
    bid = await _brand(api, h)
    cal = await api.post("/api/content/calendars", headers=h,
                         json={"brand_id": bid, "name": "Q3 Calendar"})
    assert cal.status_code == 201

    blog = (await api.post("/api/content", headers=h, json={
        "brand_id": bid, "channel": "blog", "title": "Big Post",
        "body": "Long form content here."})).json()
    repurposed = await api.post(f"/api/content/{blog['id']}/repurpose", headers=h,
                                json={"channels": ["linkedin", "twitter"]})
    assert repurposed.status_code == 200
    assert len(repurposed.json()) == 2
    assert all(i["state"] == "draft" for i in repurposed.json())
