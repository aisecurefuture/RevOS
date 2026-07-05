"""Persona identity + consent (Phase 3 M2).

Status is derived from actual media + consent state, never set directly —
these tests pin down every transition, especially that revocation is terminal
and immediately blocks reuse.
"""

from __future__ import annotations

import pytest


async def _register_owner(api, email="owner@test.com"):
    r = await api.post("/api/auth/register", json={
        "email": email, "password": "OwnerPass123", "full_name": "Owner",
    })
    assert r.status_code == 201, r.text
    return {"X-CSRF-Token": r.json()["csrf_token"]}


async def _login(api, email, password):
    r = await api.post("/api/auth/login", json={"email": email, "password": password})
    assert r.status_code == 200, r.text
    return {"X-CSRF-Token": r.json()["csrf_token"]}


async def _create_identity(api, h, name="Jordan"):
    r = await api.post("/api/personas", headers=h, json={"name": name})
    assert r.status_code == 201, r.text
    return r.json()["id"]


def _upload_headers(h):
    # multipart requests must not carry the JSON content-type from other calls
    return {"X-CSRF-Token": h["X-CSRF-Token"]}


# ---------------------------------------------------------------------------
# Status derivation across the full lifecycle
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_status_progresses_draft_to_ready_to_revoked(api):
    h = await _register_owner(api)
    pid = await _create_identity(api, h)

    got = (await api.get(f"/api/personas/{pid}", headers=h)).json()
    assert got["status"] == "draft"

    # Upload a training video -> pending_consent (media present, no consent yet).
    up = await api.post(
        f"/api/personas/{pid}/training-video", headers=_upload_headers(h),
        files={"file": ("clip.mp4", b"fake video bytes", "video/mp4")},
    )
    assert up.status_code == 200, up.text
    assert up.json()["status"] == "pending_consent"
    assert up.json()["training_video_path"]

    # Grant consent -> ready.
    consent = await api.post(f"/api/personas/{pid}/consent", headers=h, json={
        "subject_name": "Jordan Smith", "subject_email": "jordan@example.com",
        "consent_statement": "I, Jordan Smith, consent to RevOS creating an AI avatar of my likeness and voice for marketing use.",
    })
    assert consent.status_code == 201, consent.text
    assert (await api.get(f"/api/personas/{pid}", headers=h)).json()["status"] == "ready"

    # Revoke -> terminal revoked state.
    rev = await api.post(f"/api/personas/{pid}/consent/revoke", headers=h)
    assert rev.status_code == 200, rev.text
    assert rev.json()["status"] == "revoked"


@pytest.mark.asyncio
async def test_revoked_identity_cannot_be_edited_or_reused(api):
    h = await _register_owner(api)
    pid = await _create_identity(api, h)
    await api.post(
        f"/api/personas/{pid}/training-video", headers=_upload_headers(h),
        files={"file": ("clip.mp4", b"video", "video/mp4")},
    )
    await api.post(f"/api/personas/{pid}/consent", headers=h, json={
        "subject_name": "Jordan", "subject_email": "jordan@example.com",
        "consent_statement": "I consent to my likeness being used for AI avatar generation by RevOS.",
    })
    await api.post(f"/api/personas/{pid}/consent/revoke", headers=h)

    edit = await api.patch(f"/api/personas/{pid}", headers=h, json={"name": "New name"})
    assert edit.status_code == 409

    up2 = await api.post(
        f"/api/personas/{pid}/voice-sample", headers=_upload_headers(h),
        files={"file": ("v.mp3", b"audio", "audio/mpeg")},
    )
    assert up2.status_code == 409


@pytest.mark.asyncio
async def test_double_consent_rejected(api):
    h = await _register_owner(api)
    pid = await _create_identity(api, h)
    body = {
        "subject_name": "Jordan", "subject_email": "jordan@example.com",
        "consent_statement": "I consent to RevOS using my likeness and voice for AI-generated marketing content.",
    }
    first = await api.post(f"/api/personas/{pid}/consent", headers=h, json=body)
    assert first.status_code == 201
    second = await api.post(f"/api/personas/{pid}/consent", headers=h, json=body)
    assert second.status_code == 409


@pytest.mark.asyncio
async def test_placeholder_consent_statement_rejected(api):
    h = await _register_owner(api)
    pid = await _create_identity(api, h)
    r = await api.post(f"/api/personas/{pid}/consent", headers=h, json={
        "subject_name": "Jordan", "subject_email": "jordan@example.com",
        "consent_statement": "yes ok",  # too short — Pydantic min_length=20 catches this
    })
    assert r.status_code == 422


@pytest.mark.asyncio
async def test_upload_validates_mime_and_size(api):
    h = await _register_owner(api)
    pid = await _create_identity(api, h)

    wrong_mime = await api.post(
        f"/api/personas/{pid}/training-video", headers=_upload_headers(h),
        files={"file": ("note.txt", b"not a video", "text/plain")},
    )
    assert wrong_mime.status_code == 400
    assert wrong_mime.json()["error"]["code"] == "invalid_mime"

    empty = await api.post(
        f"/api/personas/{pid}/voice-sample", headers=_upload_headers(h),
        files={"file": ("v.mp3", b"", "audio/mpeg")},
    )
    assert empty.status_code == 400
    assert empty.json()["error"]["code"] == "empty_file"


@pytest.mark.asyncio
async def test_reference_images_add_and_remove(api):
    h = await _register_owner(api)
    pid = await _create_identity(api, h)

    up = await api.post(
        f"/api/personas/{pid}/reference-images", headers=_upload_headers(h),
        files={"file": ("face.jpg", b"fake image bytes", "image/jpeg")},
    )
    assert up.status_code == 200, up.text
    paths = up.json()["reference_image_paths"]
    assert len(paths) == 1
    assert up.json()["status"] == "pending_consent"  # media present, no consent

    rm = await api.delete(
        f"/api/personas/{pid}/reference-images", headers=h, params={"path": paths[0]},
    )
    assert rm.status_code == 200, rm.text
    assert rm.json()["reference_image_paths"] == []
    assert rm.json()["status"] == "draft"  # no media left -> back to draft


# ---------------------------------------------------------------------------
# Permissions
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_editor_can_create_and_upload_but_not_consent(api, make_user):
    from app.models.user import Role

    await _register_owner(api)
    ed = await _login(api, **await make_user("ed@test.com", "EditorPass123", Role.editor))
    pid = await _create_identity(api, ed, name="Editor's persona")

    up = await api.post(
        f"/api/personas/{pid}/training-video", headers=_upload_headers(ed),
        files={"file": ("clip.mp4", b"video", "video/mp4")},
    )
    assert up.status_code == 200

    consent = await api.post(f"/api/personas/{pid}/consent", headers=ed, json={
        "subject_name": "X", "subject_email": "x@example.com",
        "consent_statement": "I consent to my likeness being used for AI avatar generation.",
    })
    assert consent.status_code == 403  # editor cannot grant consent — admin+ only


@pytest.mark.asyncio
async def test_viewer_cannot_create_identity(api, make_user):
    from app.models.user import Role

    await _register_owner(api)
    v = await _login(api, **await make_user("viewer@test.com", "ViewerPass123", Role.viewer))
    r = await api.post("/api/personas", headers=v, json={"name": "X"})
    assert r.status_code == 403


# ---------------------------------------------------------------------------
# Cross-account isolation
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_cross_account_identity_is_404(api, make_client):
    h = await _register_owner(api)
    pid = await _create_identity(api, h)

    other = await make_client()
    r2 = await other.post("/api/auth/register", json={
        "email": "other@test.com", "password": "OwnerPass123", "full_name": "Other",
    })
    oh = {"X-CSRF-Token": r2.json()["csrf_token"]}
    assert (await other.get(f"/api/personas/{pid}", headers=oh)).status_code == 404
