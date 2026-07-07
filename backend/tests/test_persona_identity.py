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


# ---------------------------------------------------------------------------
# Voice sample normalization (pitch/speed bug fix)
# ---------------------------------------------------------------------------

def _tiny_wav(sample_rate: int) -> bytes:
    import io
    import struct
    import wave

    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(sample_rate)
        w.writeframes(struct.pack("<8h", *range(8)))
    return buf.getvalue()


@pytest.mark.asyncio
async def test_voice_sample_is_normalized_to_24khz_mono_wav(api, async_session_factory):
    """Regression: XTTS is sensitive to non-standard sample rates/containers —
    every uploaded voice sample should be transcoded to a clean 24kHz mono WAV
    regardless of what was uploaded, so pitch/speed can't get corrupted."""
    import wave

    h = await _register_owner(api)
    pid = await _create_identity(api, h)
    up = await api.post(
        f"/api/personas/{pid}/voice-sample", headers=_upload_headers(h),
        files={"file": ("weird.wav", _tiny_wav(8000), "audio/wav")},
    )
    assert up.status_code == 200, up.text
    path = up.json()["voice_sample_path"]
    assert path.endswith(".wav")

    from app.services.storage_service import get_storage
    data = get_storage().read(path)
    assert data[:4] == b"RIFF"
    with wave.open(__import__("io").BytesIO(data)) as w:
        assert w.getframerate() == 24000
        assert w.getnchannels() == 1


@pytest.mark.asyncio
async def test_voice_sample_upload_survives_unrecognizable_audio(api):
    """ffmpeg normalization must fail OPEN (keep the original bytes) rather
    than block the upload — voice cloning is best-effort, not a hard gate."""
    h = await _register_owner(api)
    pid = await _create_identity(api, h)
    up = await api.post(
        f"/api/personas/{pid}/voice-sample", headers=_upload_headers(h),
        files={"file": ("garbage.wav", b"not a real audio file", "audio/wav")},
    )
    assert up.status_code == 200, up.text
    assert up.json()["voice_sample_path"]


@pytest.mark.asyncio
async def test_short_voice_sample_warns_to_upload_longer(api):
    """A clip under the recommended ~60s should surface a warning so the user
    knows more reference audio improves cloning quality — but must not block
    the upload."""
    h = await _register_owner(api)
    pid = await _create_identity(api, h)
    up = await api.post(
        f"/api/personas/{pid}/voice-sample", headers=_upload_headers(h),
        files={"file": ("short.wav", _tiny_wav(24000), "audio/wav")},
    )
    assert up.status_code == 200, up.text
    body = up.json()
    assert body["voice_sample_path"]
    assert body["voice_sample_warning"] is not None
    assert "60" in body["voice_sample_warning"]


@pytest.mark.asyncio
async def test_long_voice_sample_has_no_warning(api):
    import io
    import struct
    import wave

    h = await _register_owner(api)
    pid = await _create_identity(api, h)

    buf = io.BytesIO()
    sr = 8000
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(sr)
        n = sr * 65  # 65 seconds — over the 60s recommendation
        w.writeframes(struct.pack(f"<{n}h", *([0] * n)))

    up = await api.post(
        f"/api/personas/{pid}/voice-sample", headers=_upload_headers(h),
        files={"file": ("long.wav", buf.getvalue(), "audio/wav")},
    )
    assert up.status_code == 200, up.text
    assert up.json()["voice_sample_warning"] is None


@pytest.mark.asyncio
async def test_grant_consent_notifies_the_subject(api, monkeypatch):
    """The named consent subject — not just whoever clicked 'grant' — gets a
    receipt email with a dispute path, since an admin records consent on the
    subject's behalf and could misrepresent it."""
    sent = {}

    def _capture(*, to_email, subject, html, text=""):
        sent.update(to_email=to_email, subject=subject, html=html, text=text)

    from app.services import persona_identity_service as svc
    monkeypatch.setattr(svc, "send_transactional", _capture)

    h = await _register_owner(api)
    pid = await _create_identity(api, h)
    await api.post(
        f"/api/personas/{pid}/training-video", headers=_upload_headers(h),
        files={"file": ("clip.mp4", b"video", "video/mp4")},
    )
    r = await api.post(f"/api/personas/{pid}/consent", headers=h, json={
        "subject_name": "Jordan Smith", "subject_email": "jordan@example.com",
        "consent_statement": "I, Jordan Smith, consent to RevOS creating an AI avatar of my likeness and voice.",
    })
    assert r.status_code == 201, r.text
    assert sent["to_email"] == "jordan@example.com"
    assert "did NOT authorize" in sent["html"]
    assert "support@" in sent["html"]
    assert "did NOT authorize" in sent["text"]
