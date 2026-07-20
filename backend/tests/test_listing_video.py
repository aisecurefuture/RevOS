"""Listing Video Studio (feature-flagged).

Pins the pure helpers (Fair Housing guard, deterministic script drafting,
photo timeline math) and exercises the full job lifecycle with the stub TTS
backend and a stubbed Remotion render: create -> voiceover -> render ->
succeeded -> download.
"""

from __future__ import annotations

import json
import uuid

import pytest

from app.schemas.listing_video import ListingDetails
from app.services import listing_video_service as svc


def _details(**overrides) -> dict:
    base = {
        "street": "412 Sheridan Rd",
        "city": "Winthrop Harbor",
        "state": "IL",
        "zip_code": "60096",
        "beds": 4,
        "baths": 2.5,
        "sqft": 2450,
        "price_text": "$489,000",
        "features": ["Chef's kitchen", "Lake Michigan views", "3-car garage"],
        "agent_name": "Jane Doe",
        "brokerage": "Harbor Realty",
    }
    base.update(overrides)
    return base


# ---------------------------------------------------------------------------
# Fair Housing guard
# ---------------------------------------------------------------------------

def test_fair_housing_clean_text_has_no_flags():
    assert svc.fair_housing_flags(
        "Welcome to 412 Sheridan Rd. This home offers 4 bedrooms and a chef's kitchen."
    ) == []


def test_fair_housing_flags_steering_language():
    flags = svc.fair_housing_flags(
        "Safe neighborhood, perfect for young families, walking distance to church."
    )
    lowered = [f.lower() for f in flags]
    assert "safe neighborhood" in lowered
    assert "perfect for young families" in lowered
    assert any("walking distance" in f for f in lowered)


def test_fair_housing_is_case_insensitive_and_dedupes():
    flags = svc.fair_housing_flags("EXCLUSIVE COMMUNITY. exclusive community.")
    assert len(flags) == 1


def test_fair_housing_does_not_flag_property_descriptions():
    # "family room" describes the property, not the buyer — must NOT flag.
    assert svc.fair_housing_flags("Spacious family room and a fenced yard.") == []


# ---------------------------------------------------------------------------
# Script drafting
# ---------------------------------------------------------------------------

def test_draft_script_mentions_key_facts():
    d = ListingDetails.model_validate(_details())
    script = svc.draft_script(d)
    assert "412 Sheridan Rd" in script
    assert "Winthrop Harbor" in script
    assert "4 bedrooms" in script
    assert "2.5 bathrooms" in script
    assert "2,450 square feet" in script
    assert "$489,000" in script
    assert "Jane Doe" in script
    assert svc.fair_housing_flags(script) == []


def test_draft_script_is_deterministic():
    d = ListingDetails.model_validate(_details())
    assert svc.draft_script(d) == svc.draft_script(d)


def test_draft_script_degrades_without_optional_fields():
    d = ListingDetails.model_validate(
        {"street": "1 Elm St", "city": "Zion", "state": "IL"}
    )
    script = svc.draft_script(d)
    assert "1 Elm St" in script
    assert "Schedule your private showing" in script


# ---------------------------------------------------------------------------
# Timeline math
# ---------------------------------------------------------------------------

def test_timeline_covers_narration_and_is_contiguous():
    tl = svc.build_timeline(10, narration_frames=900)
    assert tl["total_frames"] >= 900
    cursor = tl["intro_frames"]
    for slot in tl["photos"]:
        assert slot["frame_start"] == cursor
        cursor += slot["frame_count"]
    assert cursor == tl["total_frames"] - tl["outro_frames"]


def test_timeline_enforces_minimum_per_photo_for_short_narration():
    tl = svc.build_timeline(10, narration_frames=60)  # 2s narration, 10 photos
    for slot in tl["photos"]:
        assert slot["frame_count"] >= svc.MIN_FRAMES_PER_PHOTO


def test_timeline_rejects_zero_photos():
    with pytest.raises(ValueError):
        svc.build_timeline(0, narration_frames=900)


# ---------------------------------------------------------------------------
# API lifecycle (stub TTS backend, stubbed Remotion render)
# ---------------------------------------------------------------------------

async def _register_owner(api, email="owner@listing.com"):
    r = await api.post("/api/auth/register", json={
        "email": email, "password": "OwnerPass123", "full_name": "Owner",
    })
    assert r.status_code == 201, r.text
    return {"X-CSRF-Token": r.json()["csrf_token"]}


def _enable(monkeypatch, tmp_path=None):
    from app.config import settings as app_settings
    monkeypatch.setattr(app_settings, "listing_video_enabled", True)
    monkeypatch.setattr(app_settings, "listing_video_default_voice", "default-speaker")
    monkeypatch.setattr(app_settings, "avatar_backend", "stub")
    if tmp_path is not None:
        monkeypatch.setattr(app_settings, "pitch_video_remotion_dir", str(tmp_path))


def _photo_files(n: int):
    return [("photos", (f"p{i}.jpg", b"\xff\xd8\xd9" + bytes([i]), "image/jpeg")) for i in range(n)]


def _form(script: str = "A lovely home in Winthrop Harbor. Schedule your showing today.") -> dict:
    return {
        "brand_slug": "acme",
        "details": json.dumps(_details()),
        "script": script,
        "music_track": "",
    }


@pytest.mark.asyncio
async def test_disabled_feature_flag_blocks_creation(api, monkeypatch):
    from app.config import settings as app_settings
    monkeypatch.setattr(app_settings, "listing_video_enabled", False)
    h = await _register_owner(api)
    await api.post("/api/brands", headers=h, json={"name": "Acme", "slug": "acme"})
    r = await api.post("/api/listing-videos", headers=h, data=_form(), files=_photo_files(3))
    assert r.status_code == 403


@pytest.mark.asyncio
async def test_draft_script_endpoint_warns_on_fair_housing(api, monkeypatch):
    _enable(monkeypatch)
    h = await _register_owner(api)
    r = await api.post("/api/listing-videos/draft-script", headers=h, json={
        "details": _details(hook="Safe neighborhood close to great schools"),
    })
    assert r.status_code == 200, r.text
    body = r.json()
    assert "412 Sheridan Rd" in body["script"]
    assert any("safe neighborhood" in f.lower() for f in body["fair_housing_flags"])


@pytest.mark.asyncio
async def test_create_rejects_fair_housing_script(api, monkeypatch):
    _enable(monkeypatch)
    h = await _register_owner(api)
    await api.post("/api/brands", headers=h, json={"name": "Acme", "slug": "acme"})
    r = await api.post(
        "/api/listing-videos", headers=h,
        data=_form(script="A beautiful home, perfect for young families."),
        files=_photo_files(3),
    )
    assert r.status_code == 400
    assert "Fair Housing" in r.json()["error"]["message"]
    assert r.json()["error"]["code"] == "fair_housing_violation"


@pytest.mark.asyncio
async def test_create_rejects_too_few_photos(api, monkeypatch):
    _enable(monkeypatch)
    h = await _register_owner(api)
    await api.post("/api/brands", headers=h, json={"name": "Acme", "slug": "acme"})
    r = await api.post("/api/listing-videos", headers=h, data=_form(), files=_photo_files(2))
    assert r.status_code == 400


@pytest.mark.asyncio
async def test_full_job_lifecycle(api, async_session_factory, monkeypatch, tmp_path):
    _enable(monkeypatch, tmp_path)
    h = await _register_owner(api)
    await api.post("/api/brands", headers=h, json={"name": "Acme", "slug": "acme"})

    created = await api.post("/api/listing-videos", headers=h, data=_form(), files=_photo_files(5))
    assert created.status_code == 201, created.text
    job_id = created.json()["id"]
    assert created.json()["status"] == "queued"
    assert created.json()["photo_count"] == 5
    assert created.json()["speaker_name"] == "default-speaker"

    # Stage 1: voiceover (as the avatar-worker's Celery task would run it).
    from app.models.listing_video import ListingVideoJob, ListingVideoJobStatus
    async with async_session_factory() as s:
        job = await s.get(ListingVideoJob, uuid.UUID(job_id))
        await svc.run_audio_generation(s, job)
        await s.commit()
        assert job.status == ListingVideoJobStatus.rendering, job.error
        assert job.render_manifest["narration_frames"] >= 1
        assert len(job.render_manifest["timeline"]["photos"]) == 5

    # Stage 2: render — stub the `npx remotion render` subprocess call and
    # assert the props contract the Remotion side depends on.
    def _fake_render(remotion_dir, props_path, out_path, *, public_dir):
        from pathlib import Path
        props = json.loads(Path(props_path).read_text())
        assert props["address"].startswith("412 Sheridan Rd")
        assert len(props["photos"]) == 5
        assert all("/" not in p for p in props["photos"])  # filenames only
        assert props["narrationPath"] == "narration.wav"
        assert props["timeline"]["photos"][0]["frame_start"] == props["timeline"]["intro_frames"]
        Path(out_path).write_bytes(b"fake-listing-mp4")

    monkeypatch.setattr(svc, "_run_remotion_render", _fake_render)

    async with async_session_factory() as s:
        job = await s.get(ListingVideoJob, uuid.UUID(job_id))
        await svc.run_render(s, job)
        await s.commit()
        assert job.status == ListingVideoJobStatus.succeeded, job.error
        assert job.output_path

    polled = await api.get(f"/api/listing-videos/{job_id}", headers=h)
    assert polled.json()["status"] == "succeeded"
    assert polled.json()["has_output"] is True

    video = await api.get(f"/api/listing-videos/{job_id}/video", headers=h)
    assert video.status_code == 200
    assert video.content == b"fake-listing-mp4"


@pytest.mark.asyncio
async def test_cross_account_job_is_404(api, make_client, monkeypatch):
    _enable(monkeypatch)
    h = await _register_owner(api)
    await api.post("/api/brands", headers=h, json={"name": "Acme", "slug": "acme"})
    created = await api.post("/api/listing-videos", headers=h, data=_form(), files=_photo_files(3))
    job_id = created.json()["id"]

    other = await make_client()
    r2 = await other.post("/api/auth/register", json={
        "email": "other@listing.com", "password": "OwnerPass123", "full_name": "Other",
    })
    oh = {"X-CSRF-Token": r2.json()["csrf_token"]}
    assert (await other.get(f"/api/listing-videos/{job_id}", headers=oh)).status_code == 404
