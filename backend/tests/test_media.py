"""Media pipeline: upload, render, preserve original, approve (Module 11)."""

from __future__ import annotations

import hashlib
from io import BytesIO

import pytest
from app.models.user import Role
from PIL import Image


def _png(w: int = 2000, h: int = 1000) -> bytes:
    buf = BytesIO()
    Image.new("RGB", (w, h), (120, 80, 200)).save(buf, "PNG")
    return buf.getvalue()


async def _login(api, email, password):
    r = await api.post("/api/auth/login", json={"email": email, "password": password})
    assert r.status_code == 200, r.text
    return {"X-CSRF-Token": r.json()["csrf_token"]}


async def _brand(api, h):
    return (await api.post("/api/brands", headers=h, json={"name": "Media Brand"})).json()["id"]


@pytest.mark.asyncio
async def test_upload_probes_dimensions(api, make_user):
    h = await _login(api, **await make_user("admin@test.com", "AdminPass123", Role.admin))
    bid = await _brand(api, h)
    resp = await api.post("/api/media", headers=h,
                          files={"file": ("hero.png", _png(), "image/png")},
                          data={"brand_id": bid})
    assert resp.status_code == 201
    asset = resp.json()
    assert asset["kind"] == "image"
    assert asset["width"] == 2000 and asset["height"] == 1000
    assert asset["status"] == "uploaded"


@pytest.mark.asyncio
async def test_process_creates_platform_renditions(api, make_user):
    h = await _login(api, **await make_user("admin@test.com", "AdminPass123", Role.admin))
    bid = await _brand(api, h)
    aid = (await api.post("/api/media", headers=h,
                          files={"file": ("hero.png", _png(), "image/png")},
                          data={"brand_id": bid})).json()["id"]

    variants = await api.post(f"/api/media/{aid}/process", headers=h,
                              json={"platforms": ["instagram"], "enhance": False})
    assert variants.status_code == 200
    dims = {(v["purpose"], v["width"], v["height"]) for v in variants.json()}
    assert ("feed_square", 1080, 1080) in dims
    assert ("feed_portrait", 1080, 1350) in dims
    assert ("story", 1080, 1920) in dims

    detail = (await api.get(f"/api/media/{aid}")).json()
    assert detail["status"] == "ready"
    assert len(detail["variants"]) == 3


@pytest.mark.asyncio
async def test_original_is_preserved(api, make_user):
    h = await _login(api, **await make_user("admin@test.com", "AdminPass123", Role.admin))
    bid = await _brand(api, h)
    original = _png()
    aid = (await api.post("/api/media", headers=h,
                          files={"file": ("hero.png", original, "image/png")},
                          data={"brand_id": bid})).json()["id"]

    # Process (which writes variants) must NOT touch the original.
    await api.post(f"/api/media/{aid}/process", headers=h, json={"platforms": ["twitter"]})

    fetched = await api.get(f"/api/media/{aid}/original")
    assert fetched.status_code == 200
    assert hashlib.sha256(fetched.content).hexdigest() == hashlib.sha256(original).hexdigest()
    # Original dimensions on the asset are unchanged.
    asset = (await api.get(f"/api/media/{aid}")).json()
    assert asset["width"] == 2000 and asset["height"] == 1000


@pytest.mark.asyncio
async def test_enhance_and_approve_variant(api, make_user):
    h = await _login(api, **await make_user("admin@test.com", "AdminPass123", Role.admin))
    bid = await _brand(api, h)
    aid = (await api.post("/api/media", headers=h,
                          files={"file": ("hero.png", _png(), "image/png")},
                          data={"brand_id": bid})).json()["id"]
    variants = (await api.post(f"/api/media/{aid}/process", headers=h,
                               json={"platforms": ["linkedin"], "enhance": True})).json()
    vid = variants[0]["id"]
    assert variants[0]["state"] == "draft"

    approved = await api.post(f"/api/media/variants/{vid}/approve", headers=h)
    assert approved.json()["state"] == "approved"

    # Variant file is downloadable.
    file_resp = await api.get(f"/api/media/variants/{vid}/file")
    assert file_resp.status_code == 200
    assert file_resp.headers["content-type"] == "image/jpeg"


@pytest.mark.asyncio
async def test_invalid_video_degrades_gracefully(api, make_user):
    h = await _login(api, **await make_user("admin@test.com", "AdminPass123", Role.admin))
    bid = await _brand(api, h)
    aid = (await api.post("/api/media", headers=h,
                          files={"file": ("clip.mp4", b"not a real video", "video/mp4")},
                          data={"brand_id": bid})).json()["id"]
    # ffmpeg fails on invalid input -> variants skipped, asset still ready.
    variants = await api.post(f"/api/media/{aid}/process", headers=h, json={})
    assert variants.status_code == 200
    assert (await api.get(f"/api/media/{aid}")).json()["status"] == "ready"


@pytest.mark.asyncio
async def test_upload_requires_editor(api, make_user):
    h = await _login(api, **await make_user("vw@test.com", "ViewerPass123", Role.viewer))
    resp = await api.post("/api/media", headers=h,
                          files={"file": ("x.png", _png(10, 10), "image/png")},
                          data={"brand_id": "00000000-0000-0000-0000-000000000000"})
    assert resp.status_code == 403
