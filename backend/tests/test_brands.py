"""Brand CRUD + RBAC + sub-resource tests (Module 5)."""

from __future__ import annotations

import pytest
from app.models.user import Role


async def _login(api, email, password):
    r = await api.post("/api/auth/login", json={"email": email, "password": password})
    assert r.status_code == 200, r.text
    return {"X-CSRF-Token": r.json()["csrf_token"]}


@pytest.mark.asyncio
async def test_brand_full_lifecycle(api, make_user):
    creds = await make_user("admin@test.com", "AdminPass123", Role.admin)
    h = await _login(api, **creds)

    created = await api.post("/api/brands", headers=h,
                             json={"name": "CyberArmor AI", "brand_type": "company"})
    assert created.status_code == 201
    body = created.json()
    assert body["slug"] == "cyberarmor-ai"
    bid = body["id"]

    listed = await api.get("/api/brands")
    assert listed.status_code == 200
    assert any(b["id"] == bid for b in listed.json())

    updated = await api.patch(f"/api/brands/{bid}", headers=h, json={"tagline": "Secure AI"})
    assert updated.status_code == 200
    assert updated.json()["tagline"] == "Secure AI"

    deleted = await api.delete(f"/api/brands/{bid}", headers=h)
    assert deleted.status_code == 200
    assert (await api.get(f"/api/brands/{bid}")).status_code == 404


@pytest.mark.asyncio
async def test_brand_slug_is_unique(api, make_user):
    h = await _login(api, **await make_user("a@test.com", "AdminPass123", Role.admin))
    s1 = (await api.post("/api/brands", headers=h, json={"name": "Dup Brand"})).json()["slug"]
    s2 = (await api.post("/api/brands", headers=h, json={"name": "Dup Brand"})).json()["slug"]
    assert s1 != s2


@pytest.mark.asyncio
async def test_editor_cannot_create_brand(api, make_user):
    h = await _login(api, **await make_user("ed@test.com", "EditorPass123", Role.editor))
    r = await api.post("/api/brands", headers=h, json={"name": "Nope"})
    assert r.status_code == 403
    assert r.json()["error"]["code"] == "insufficient_role"


@pytest.mark.asyncio
async def test_viewer_reads_but_cannot_write(api, make_user):
    h = await _login(api, **await make_user("vw@test.com", "ViewerPass123", Role.viewer))
    assert (await api.get("/api/brands")).status_code == 200
    assert (await api.post("/api/brands", headers=h, json={"name": "X"})).status_code == 403


@pytest.mark.asyncio
async def test_create_brand_requires_csrf(api, make_user):
    creds = await make_user("a2@test.com", "AdminPass123", Role.admin)
    await _login(api, **creds)  # sets cookies but we omit the header
    r = await api.post("/api/brands", json={"name": "NoCsrf"})
    assert r.status_code == 403
    assert r.json()["error"]["code"] == "csrf_failed"


@pytest.mark.asyncio
async def test_brand_rejects_javascript_url(api, make_user):
    h = await _login(api, **await make_user("a3@test.com", "AdminPass123", Role.admin))
    r = await api.post("/api/brands", headers=h,
                       json={"name": "Bad", "website_url": "javascript:alert(1)"})
    assert r.status_code == 422


@pytest.mark.asyncio
async def test_brand_strips_html_from_name(api, make_user):
    h = await _login(api, **await make_user("a6@test.com", "AdminPass123", Role.admin))
    r = await api.post("/api/brands", headers=h,
                       json={"name": "Acme <script>alert(1)</script>Co"})
    assert r.status_code == 201
    assert "<script>" not in r.json()["name"]


@pytest.mark.asyncio
async def test_brand_subresources(api, make_user):
    h = await _login(api, **await make_user("a5@test.com", "AdminPass123", Role.admin))
    bid = (await api.post("/api/brands", headers=h, json={"name": "Sub Brand"})).json()["id"]

    assert (await api.post(f"/api/brands/{bid}/audiences", headers=h,
                           json={"name": "CISOs"})).status_code == 201
    assert (await api.post(f"/api/brands/{bid}/personas", headers=h,
                           json={"name": "CISO Carla", "goals": ["reduce risk"]})).status_code == 201
    voice = await api.put(f"/api/brands/{bid}/voice", headers=h,
                          json={"tone": "authoritative", "do_list": ["be concise"]})
    assert voice.status_code == 200

    detail = (await api.get(f"/api/brands/{bid}")).json()
    assert len(detail["audiences"]) == 1
    assert len(detail["personas"]) == 1
    assert detail["voice"]["tone"] == "authoritative"
