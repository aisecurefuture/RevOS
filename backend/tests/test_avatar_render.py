"""Render pipeline (Phase 3 M6) — captions + platform framing, then attach
the finished avatar video to a SocialPost that flows through the existing
approval queue.
"""

from __future__ import annotations

import uuid

import pytest

from app.services import avatar_render_service, avatar_service


async def _register_owner(api):
    r = await api.post("/api/auth/register", json={
        "email": "owner@test.com", "password": "OwnerPass123", "full_name": "Owner",
    })
    assert r.status_code == 201, r.text
    return {"X-CSRF-Token": r.json()["csrf_token"]}


def _csrf(h):
    return {"X-CSRF-Token": h["X-CSRF-Token"]}


async def _ready_persona_with_brand(api, h, brand_id):
    pid = (await api.post("/api/personas", headers=h, json={
        "name": "Persona", "brand_id": brand_id,
    })).json()["id"]
    await api.post(f"/api/personas/{pid}/training-video", headers=_csrf(h),
                   files={"file": ("v.mp4", b"training-video-bytes", "video/mp4")})
    await api.post(f"/api/personas/{pid}/voice-sample", headers=_csrf(h),
                   files={"file": ("a.mp3", b"voice-sample-bytes", "audio/mpeg")})
    await api.post(f"/api/personas/{pid}/consent", headers=h, json={
        "subject_name": "Subject", "subject_email": "subject@example.com",
        "consent_statement": "I consent to RevOS creating an AI avatar of my likeness and voice.",
    })
    return pid


async def _seed_connection(async_session_factory, account_id, user_id, platform):
    from app.models.social_connection import SocialConnection, SocialConnectionStatus

    async with async_session_factory() as s:
        conn = SocialConnection(
            account_id=account_id, platform=platform, external_id="ext-1",
            handle="acct", display_name="Acct", status=SocialConnectionStatus.active,
            token_ref=f"revos/accounts/{account_id}/social/{platform}/x",
            connected_by=user_id,
        )
        s.add(conn)
        await s.commit()


async def _succeeded_job(api, async_session_factory, h, brand_id, app_settings, monkeypatch, script="Hi there everyone, check this out today."):
    monkeypatch.setattr(app_settings, "avatar_backend", "stub")
    pid = await _ready_persona_with_brand(api, h, brand_id)
    job = (await api.post("/api/avatar/jobs", headers=h, json={
        "persona_identity_id": pid, "script": script, "target_seconds": 15,
    })).json()

    from app.models.avatar_job import AvatarVideoJob
    async with async_session_factory() as s:
        j = await s.get(AvatarVideoJob, uuid.UUID(job["id"]))
        await avatar_service.run_generation(s, j)
        await s.commit()
    return job["id"]


# ---------------------------------------------------------------------------
# Caption chunking (pure, no ffmpeg required)
# ---------------------------------------------------------------------------

def test_caption_chunks_span_the_full_duration():
    script = "one two three four five six seven eight nine ten eleven twelve"
    chunks = avatar_render_service._caption_chunks(script, 12)
    assert chunks[0][0] == 0.0
    assert chunks[-1][1] == 12.0
    # every word appears somewhere in the chunk text
    joined = " ".join(c[2] for c in chunks)
    for word in script.split():
        assert word in joined


def test_caption_chunks_empty_script_returns_nothing():
    assert avatar_render_service._caption_chunks("   ", 15) == []


def test_escape_drawtext_neutralizes_special_chars():
    escaped = avatar_render_service._escape_drawtext("50% off: don't wait")
    assert "\\%" in escaped
    assert "\\:" in escaped
    assert "'" not in escaped  # smart-quoted, not left raw


# ---------------------------------------------------------------------------
# publish_avatar_job — the render → post → approval seam
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_publish_requires_a_finished_job(api, async_session_factory):
    from app.core.exceptions import ConflictError
    from app.models.avatar_job import AvatarVideoJob

    h = await _register_owner(api)
    bid = (await api.post("/api/brands", headers=h, json={"name": "Acme"})).json()["id"]
    pid = await _ready_persona_with_brand(api, h, bid)
    job = (await api.post("/api/avatar/jobs", headers=h, json={
        "persona_identity_id": pid, "script": "Hello world today.", "target_seconds": 7,
    })).json()

    me = (await api.get("/api/auth/me", headers=h)).json()
    async with async_session_factory() as s:
        from app.models.user import AdminUser

        j = await s.get(AvatarVideoJob, uuid.UUID(job["id"]))  # still queued
        user = await s.get(AdminUser, uuid.UUID(me["id"]))
        with pytest.raises(ConflictError):
            await avatar_render_service.publish_avatar_job(
                s, j, j.account_id, user, platform="facebook",
            )


@pytest.mark.asyncio
async def test_publish_attaches_video_and_submits_for_approval(api, async_session_factory, monkeypatch):
    from app.config import settings as app_settings
    from app.models.avatar_job import AvatarVideoJob
    from app.models.social import SocialPost
    from app.models.user import AdminUser

    h = await _register_owner(api)
    me = (await api.get("/api/auth/me", headers=h)).json()
    bid = (await api.post("/api/brands", headers=h, json={"name": "Acme"})).json()["id"]
    job_id = await _succeeded_job(api, async_session_factory, h, bid, app_settings, monkeypatch)

    async with async_session_factory() as s:
        j = await s.get(AvatarVideoJob, uuid.UUID(job_id))
        assert j.status == "succeeded" and j.output_path
        await _seed_connection(async_session_factory, j.account_id, uuid.UUID(me["id"]), "facebook")

    async with async_session_factory() as s:
        j = await s.get(AvatarVideoJob, uuid.UUID(job_id))
        user = await s.get(AdminUser, uuid.UUID(me["id"]))
        post, approval = await avatar_render_service.publish_avatar_job(
            s, j, j.account_id, user, platform="facebook", burn_captions_on=False,
        )
        await s.commit()
        post_id, approval_id = post.id, approval.id

    async with async_session_factory() as s:
        post = await s.get(SocialPost, post_id)
        assert post.brand_id == uuid.UUID(bid)
        assert post.media_urls  # a rendered/registered media key was attached
        assert post.state == "needs_review"

    approvals = (await api.get("/api/approvals", headers=h)).json()
    assert any(a["id"] == str(approval_id) for a in approvals)


@pytest.mark.asyncio
async def test_publish_endpoint_end_to_end(api, async_session_factory, monkeypatch):
    from app.config import settings as app_settings
    from app.models.avatar_job import AvatarVideoJob

    h = await _register_owner(api)
    me = (await api.get("/api/auth/me", headers=h)).json()
    bid = (await api.post("/api/brands", headers=h, json={"name": "Acme"})).json()["id"]
    job_id = await _succeeded_job(api, async_session_factory, h, bid, app_settings, monkeypatch)

    async with async_session_factory() as s:
        j = await s.get(AvatarVideoJob, uuid.UUID(job_id))
        await _seed_connection(async_session_factory, j.account_id, uuid.UUID(me["id"]), "youtube")

    r = await api.post(f"/api/avatar/jobs/{job_id}/publish", headers=h, json={
        "platform": "youtube", "caption": "New drop 🎬", "burn_captions": False,
    })
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["platform"] == "youtube"
    assert body["post_id"] and body["approval_request_id"]
