"""Email API: test send, templates, suppressions, preview, RBAC (Module 7)."""

from __future__ import annotations

import pytest
from app.models.user import Role


async def _login(api, email, password):
    r = await api.post("/api/auth/login", json={"email": email, "password": password})
    assert r.status_code == 200, r.text
    return {"X-CSRF-Token": r.json()["csrf_token"]}


async def _brand(api, headers):
    return (await api.post("/api/brands", headers=headers, json={"name": "Mail Brand"})).json()["id"]


@pytest.mark.asyncio
async def test_test_send_records_message(api, make_user):
    h = await _login(api, **await make_user("admin@test.com", "AdminPass123", Role.admin))
    bid = await _brand(api, h)
    r = await api.post("/api/emails/test", headers=h, json={
        "brand_id": bid, "to_email": "me@x.com", "subject": "Ping",
        "html_body": "<p>Hello</p>"})
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "sent"
    assert body["test_mode"] is True


@pytest.mark.asyncio
async def test_test_send_requires_admin(api, make_user):
    h = await _login(api, **await make_user("ed@test.com", "EditorPass123", Role.editor))
    # Editor must create the brand via an admin; here just assert the send is blocked.
    r = await api.post("/api/emails/test", headers=h, json={
        "brand_id": "00000000-0000-0000-0000-000000000000",
        "to_email": "me@x.com", "subject": "x", "html_body": "<p>x</p>"})
    assert r.status_code == 403


@pytest.mark.asyncio
async def test_template_crud_and_preview_autoescapes(api, make_user):
    h = await _login(api, **await make_user("admin@test.com", "AdminPass123", Role.admin))
    created = await api.post("/api/email-templates", headers=h, json={
        "name": "Welcome", "subject": "Hi {{first_name}}",
        "html_body": "<p>Welcome {{first_name}}</p>", "category": "welcome"})
    assert created.status_code == 201
    assert created.json()["slug"] == "welcome"

    listed = await api.get("/api/email-templates")
    assert any(t["slug"] == "welcome" for t in listed.json())

    # Preview must autoescape injected context (XSS defense).
    preview = await api.post("/api/emails/preview", headers=h, json={
        "subject": "Hi {{first_name}}", "html_body": "<p>{{first_name}}</p>",
        "context": {"first_name": "<script>alert(1)</script>"}})
    assert preview.status_code == 200
    assert "<script>" not in preview.json()["html"]
    assert "&lt;script&gt;" in preview.json()["html"]


@pytest.mark.asyncio
async def test_suppressions_admin_only(api, make_user):
    admin_h = await _login(api, **await make_user("admin@test.com", "AdminPass123", Role.admin))
    add = await api.post("/api/suppressions", headers=admin_h,
                         json={"email": "block@x.com", "reason": "manual"})
    assert add.status_code == 201
    sid = add.json()["id"]
    assert any(s["email"] == "block@x.com" for s in (await api.get("/api/suppressions")).json())
    assert (await api.delete(f"/api/suppressions/{sid}", headers=admin_h)).status_code == 200

    editor_h = await _login(api, **await make_user("ed@test.com", "EditorPass123", Role.editor))
    assert (await api.get("/api/suppressions", headers=editor_h)).status_code == 403
