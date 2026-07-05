"""Avatar video generation (Phase 3 M3).

Exercises the full job lifecycle with the stub backend (no ML stack): create →
generate → succeeded → download, plus the guards that make it safe — a persona
must be consent-ready to start a job, and a persona revoked *after* a job is
queued must still be refused at generation time.
"""

from __future__ import annotations

import uuid

import pytest

from app.services import avatar_service


async def _register_owner(api, email="owner@test.com"):
    r = await api.post("/api/auth/register", json={
        "email": email, "password": "OwnerPass123", "full_name": "Owner",
    })
    assert r.status_code == 201, r.text
    return {"X-CSRF-Token": r.json()["csrf_token"]}


def _csrf(h):
    return {"X-CSRF-Token": h["X-CSRF-Token"]}


async def _ready_persona(api, h, name="Persona"):
    pid = (await api.post("/api/personas", headers=h, json={"name": name})).json()["id"]
    await api.post(f"/api/personas/{pid}/training-video", headers=_csrf(h),
                   files={"file": ("v.mp4", b"training-video-bytes", "video/mp4")})
    await api.post(f"/api/personas/{pid}/voice-sample", headers=_csrf(h),
                   files={"file": ("a.mp3", b"voice-sample-bytes", "audio/mpeg")})
    await api.post(f"/api/personas/{pid}/consent", headers=h, json={
        "subject_name": "Subject", "subject_email": "subject@example.com",
        "consent_statement": "I consent to RevOS creating an AI avatar of my likeness and voice.",
    })
    return pid


async def _run(async_session_factory, job_id):
    from app.models.avatar_job import AvatarVideoJob
    async with async_session_factory() as s:
        job = await s.get(AvatarVideoJob, uuid.UUID(job_id))
        await avatar_service.run_generation(s, job)
        await s.commit()


# ---------------------------------------------------------------------------
# Estimates + durations
# ---------------------------------------------------------------------------

def test_estimate_seconds_matches_measured_rate():
    # 15s at 30fps × 1.7s/frame ≈ 765s (~13 min) — the measured spike figure.
    assert avatar_service.estimate_seconds(15) == 765
    assert avatar_service.estimate_seconds(120) == 6120


@pytest.mark.asyncio
async def test_durations_endpoint(api):
    h = await _register_owner(api)
    d = (await api.get("/api/avatar/durations", headers=h)).json()["durations"]
    assert [x["seconds"] for x in d] == [7, 15, 30, 45, 60, 90, 120]
    assert all(x["estimated_seconds"] > 0 for x in d)


# ---------------------------------------------------------------------------
# Create-job guards
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_cannot_create_job_for_unready_persona(api):
    h = await _register_owner(api)
    # A bare persona (no media, no consent) is 'draft'.
    pid = (await api.post("/api/personas", headers=h, json={"name": "Draft"})).json()["id"]
    r = await api.post("/api/avatar/jobs", headers=h, json={
        "persona_identity_id": pid, "script": "Hi there everyone.", "target_seconds": 15,
    })
    assert r.status_code == 409


@pytest.mark.asyncio
async def test_invalid_duration_rejected(api):
    h = await _register_owner(api)
    pid = await _ready_persona(api, h)
    r = await api.post("/api/avatar/jobs", headers=h, json={
        "persona_identity_id": pid, "script": "Hi.", "target_seconds": 42,
    })
    assert r.status_code == 400
    assert r.json()["error"]["code"] == "invalid_duration"


@pytest.mark.asyncio
async def test_viewer_cannot_create_job(api, make_user):
    from app.models.user import Role

    await _register_owner(api)
    v = await api.post("/api/auth/login", json={"email": (await make_user("v@test.com", "ViewerPass123", Role.viewer))["email"], "password": "ViewerPass123"})
    vh = {"X-CSRF-Token": v.json()["csrf_token"]}
    r = await api.post("/api/avatar/jobs", headers=vh, json={
        "persona_identity_id": str(uuid.uuid4()), "script": "Hi.", "target_seconds": 15,
    })
    assert r.status_code == 403


# ---------------------------------------------------------------------------
# Full lifecycle (stub backend)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_generate_succeeds_and_downloads(api, async_session_factory, monkeypatch):
    from app.config import settings as app_settings
    monkeypatch.setattr(app_settings, "avatar_backend", "stub")

    h = await _register_owner(api)
    pid = await _ready_persona(api, h)

    created = await api.post("/api/avatar/jobs", headers=h, json={
        "persona_identity_id": pid,
        "script": "Welcome to RevOS — this is a test of avatar generation.",
        "target_seconds": 15,
    })
    assert created.status_code == 201, created.text
    job = created.json()
    assert job["status"] == "queued"
    assert job["estimated_seconds"] == 765
    jid = job["id"]

    # No video yet.
    assert (await api.get(f"/api/avatar/jobs/{jid}/video", headers=h)).status_code == 404

    await _run(async_session_factory, jid)

    got = (await api.get(f"/api/avatar/jobs/{jid}", headers=h)).json()
    assert got["status"] == "succeeded"
    assert got["has_output"] is True
    assert got["error"] is None

    vid = await api.get(f"/api/avatar/jobs/{jid}/video", headers=h)
    assert vid.status_code == 200
    assert vid.headers["content-type"] == "video/mp4"
    assert vid.headers["content-disposition"].startswith("attachment")
    assert len(vid.content) > 0


@pytest.mark.asyncio
async def test_revoked_after_queue_fails_generation(api, async_session_factory, monkeypatch):
    """A persona whose consent is revoked after a job is queued must never
    actually generate — the guard is re-checked at generation time."""
    from app.config import settings as app_settings
    monkeypatch.setattr(app_settings, "avatar_backend", "stub")

    h = await _register_owner(api)
    pid = await _ready_persona(api, h)
    jid = (await api.post("/api/avatar/jobs", headers=h, json={
        "persona_identity_id": pid, "script": "Hello world from the avatar.", "target_seconds": 7,
    })).json()["id"]

    # Revoke consent before the worker runs.
    await api.post(f"/api/personas/{pid}/consent/revoke", headers=h)

    await _run(async_session_factory, jid)

    got = (await api.get(f"/api/avatar/jobs/{jid}", headers=h)).json()
    assert got["status"] == "failed"
    assert "consent" in (got["error"] or "").lower() or "usable" in (got["error"] or "").lower()


@pytest.mark.asyncio
async def test_generation_fails_cleanly_when_backend_unconfigured(api, async_session_factory, monkeypatch):
    from app.config import settings as app_settings
    monkeypatch.setattr(app_settings, "avatar_backend", "none")

    h = await _register_owner(api)
    pid = await _ready_persona(api, h)
    jid = (await api.post("/api/avatar/jobs", headers=h, json={
        "persona_identity_id": pid, "script": "Hi there.", "target_seconds": 7,
    })).json()["id"]

    await _run(async_session_factory, jid)

    got = (await api.get(f"/api/avatar/jobs/{jid}", headers=h)).json()
    assert got["status"] == "failed"
    assert "backend" in (got["error"] or "").lower()
