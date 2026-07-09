"""Pitch Video Studio (feature-flagged).

Exercises the full job lifecycle with the stub TTS backend and a stubbed
Remotion render: create -> generate audio -> render -> succeeded -> download.
Also pins the pure helpers (cache key, frame timing) and Deck Spec validation.
"""

from __future__ import annotations

import uuid

import pytest

from app.core.exceptions import RevOSError
from app.services import pitch_video_service as svc


def _valid_deck(brand_slug: str = "acme") -> dict:
    return {
        "brandId": brand_slug,
        "title": "Acme — Test Deck",
        "aspectRatio": "16:9",
        "voice": "test-speaker",
        "scenes": [
            {
                "id": "hero", "layout": "hero",
                "content": {"eyebrow": "Welcome", "headline": "Acme does things.", "sub": "Really."},
                "narration": "Acme does things, and does them well.",
            },
            {
                "id": "close", "layout": "close", "variant": "dark",
                "content": {"headline": "Let's talk.", "sub": "acme.example"},
                "narration": "Let's talk about what Acme can do for you.",
            },
        ],
    }


# ---------------------------------------------------------------------------
# Pure helpers
# ---------------------------------------------------------------------------

def test_cache_key_is_deterministic_and_voice_scoped():
    a = svc.cache_key("Hello world", "voice-a")
    b = svc.cache_key("Hello world", "voice-a")
    c = svc.cache_key("Hello world", "voice-b")
    assert a == b
    assert a != c


def test_seconds_to_frames_rounds_up_and_floors_at_one():
    assert svc.seconds_to_frames(1.0, fps=30) == 30
    assert svc.seconds_to_frames(1.01, fps=30) == 31  # never truncate mid-word
    assert svc.seconds_to_frames(0.0, fps=30) == 1    # at least one frame


# ---------------------------------------------------------------------------
# Deck Spec validation
# ---------------------------------------------------------------------------

def test_valid_deck_spec_parses():
    deck = svc.validate_deck_spec(_valid_deck())
    assert deck.title == "Acme — Test Deck"
    assert len(deck.scenes) == 2
    assert deck.scenes[1].variant == "dark"


def test_deck_spec_unwraps_seed_output_wrapper():
    """Pasting the seed script's whole output ({"deck_spec": {...}}) must work."""
    deck = svc.validate_deck_spec({"brand_id": "x", "brand_slug": "acme", "deck_spec": _valid_deck()})
    assert len(deck.scenes) == 2


def test_deck_spec_error_names_the_field():
    bad = _valid_deck()
    del bad["scenes"][0]["narration"]
    with pytest.raises(RevOSError) as exc_info:
        svc.validate_deck_spec(bad)
    assert "narration" in str(exc_info.value.message)


def test_deck_spec_rejects_unknown_layout():
    bad = _valid_deck()
    bad["scenes"][0]["layout"] = "not-a-real-layout"
    with pytest.raises(RevOSError):
        svc.validate_deck_spec(bad)


def test_deck_spec_rejects_content_mismatched_to_layout():
    bad = _valid_deck()
    bad["scenes"][0]["content"] = {"totally": "wrong shape"}
    with pytest.raises(RevOSError):
        svc.validate_deck_spec(bad)


def test_deck_spec_rejects_duplicate_scene_ids():
    bad = _valid_deck()
    bad["scenes"][1]["id"] = bad["scenes"][0]["id"]
    with pytest.raises(RevOSError):
        svc.validate_deck_spec(bad)


def test_deck_spec_enforces_max_scenes(monkeypatch):
    from app.config import settings as app_settings
    monkeypatch.setattr(app_settings, "pitch_video_max_scenes", 1)
    with pytest.raises(RevOSError):
        svc.validate_deck_spec(_valid_deck())  # has 2 scenes


# ---------------------------------------------------------------------------
# Full job lifecycle via the API + stage functions (stub backend, stubbed render)
# ---------------------------------------------------------------------------

async def _register_owner(api, email="owner@test.com"):
    r = await api.post("/api/auth/register", json={
        "email": email, "password": "OwnerPass123", "full_name": "Owner",
    })
    assert r.status_code == 201, r.text
    return {"X-CSRF-Token": r.json()["csrf_token"]}


def _enable(monkeypatch, tmp_path=None):
    from app.config import settings as app_settings
    monkeypatch.setattr(app_settings, "pitch_video_studio_enabled", True)
    monkeypatch.setattr(app_settings, "pitch_video_default_voice", "default-speaker")
    monkeypatch.setattr(app_settings, "avatar_backend", "stub")
    if tmp_path is not None:
        monkeypatch.setattr(app_settings, "pitch_video_remotion_dir", str(tmp_path))


@pytest.mark.asyncio
async def test_disabled_feature_flag_blocks_creation(api, monkeypatch):
    from app.config import settings as app_settings
    monkeypatch.setattr(app_settings, "pitch_video_studio_enabled", False)
    h = await _register_owner(api)
    await api.post("/api/brands", headers=h, json={"name": "Acme"})
    r = await api.post("/api/pitch-videos", headers=h, json={"deck_spec": _valid_deck()})
    assert r.status_code == 403


@pytest.mark.asyncio
async def test_unknown_brand_slug_404s(api, monkeypatch):
    _enable(monkeypatch)
    h = await _register_owner(api)
    r = await api.post("/api/pitch-videos", headers=h, json={"deck_spec": _valid_deck("no-such-brand")})
    assert r.status_code == 404


@pytest.mark.asyncio
async def test_full_job_lifecycle(api, async_session_factory, monkeypatch, tmp_path):
    _enable(monkeypatch, tmp_path)
    h = await _register_owner(api)
    await api.post("/api/brands", headers=h, json={
        "name": "Acme", "slug": "acme",
    })

    created = await api.post("/api/pitch-videos", headers=h, json={"deck_spec": _valid_deck()})
    assert created.status_code == 201, created.text
    job_id = created.json()["id"]
    assert created.json()["status"] == "queued"
    assert created.json()["voice_mode"] == "stock"
    assert created.json()["speaker_name"] == "test-speaker"  # from the deck's own "voice" field

    # Stage 1: audio generation (as the avatar-worker's Celery task would run it).
    from app.models.pitch_video import PitchVideoJob, PitchVideoJobStatus
    async with async_session_factory() as s:
        job = await s.get(PitchVideoJob, uuid.UUID(job_id))
        await svc.run_audio_generation(s, job)
        await s.commit()
        assert job.status == PitchVideoJobStatus.rendering
        assert len(job.scene_manifest) == 2
        assert job.scene_manifest[0]["frame_start"] == 0
        assert job.scene_manifest[1]["frame_start"] == job.scene_manifest[0]["frame_count"]

    # Stage 2: render — stub out the actual `npx remotion render` subprocess call.
    def _fake_render(remotion_dir, props_path, out_path, *, public_dir):
        import json
        from pathlib import Path
        props = json.loads(Path(props_path).read_text())
        assert props["scenes"][0]["layout"] == "hero"
        assert props["scenes"][0]["audioPath"] == "hero.wav"  # filename only, not an absolute path
        assert props["fps"] == 30
        assert public_dir  # a real temp dir materializing the scene audio
        Path(out_path).write_bytes(b"fake-mp4-bytes")

    monkeypatch.setattr(svc, "_run_remotion_render", _fake_render)

    async with async_session_factory() as s:
        job = await s.get(PitchVideoJob, uuid.UUID(job_id))
        await svc.run_render(s, job)
        await s.commit()
        assert job.status == PitchVideoJobStatus.succeeded
        assert job.output_path

    polled = await api.get(f"/api/pitch-videos/{job_id}", headers=h)
    assert polled.json()["status"] == "succeeded"
    assert polled.json()["has_output"] is True

    video = await api.get(f"/api/pitch-videos/{job_id}/video", headers=h)
    assert video.status_code == 200
    assert video.content == b"fake-mp4-bytes"


@pytest.mark.asyncio
async def test_cross_account_job_is_404(api, make_client, monkeypatch):
    _enable(monkeypatch)
    h = await _register_owner(api)
    await api.post("/api/brands", headers=h, json={"name": "Acme", "slug": "acme"})
    created = await api.post("/api/pitch-videos", headers=h, json={"deck_spec": _valid_deck()})
    job_id = created.json()["id"]

    other = await make_client()
    r2 = await other.post("/api/auth/register", json={
        "email": "other@test.com", "password": "OwnerPass123", "full_name": "Other",
    })
    oh = {"X-CSRF-Token": r2.json()["csrf_token"]}
    assert (await other.get(f"/api/pitch-videos/{job_id}", headers=oh)).status_code == 404


# ---------------------------------------------------------------------------
# PPTX import
# ---------------------------------------------------------------------------

def _tiny_pptx(slides: list[tuple[str, list[str]]]) -> bytes:
    """Build a minimal .pptx: one title shape + one body shape per slide."""
    import io
    import zipfile

    def slide_xml(title: str, bullets: list[str]) -> str:
        bullet_paras = "".join(
            f"<a:p><a:r><a:t>{b}</a:t></a:r></a:p>" for b in bullets
        )
        return (
            '<p:sld xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main" '
            'xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main">'
            "<p:cSld><p:spTree>"
            "<p:sp><p:nvSpPr><p:nvPr><p:ph type=\"title\"/></p:nvPr></p:nvSpPr>"
            f"<p:txBody><a:p><a:r><a:t>{title}</a:t></a:r></a:p></p:txBody></p:sp>"
            "<p:sp><p:nvSpPr><p:nvPr><p:ph type=\"body\"/></p:nvPr></p:nvSpPr>"
            f"<p:txBody>{bullet_paras}</p:txBody></p:sp>"
            "</p:spTree></p:cSld></p:sld>"
        )

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("[Content_Types].xml", "<Types/>")
        for i, (title, bullets) in enumerate(slides, start=1):
            z.writestr(f"ppt/slides/slide{i}.xml", slide_xml(title, bullets))
    return buf.getvalue()


def test_pptx_extract_slides_titles_and_bodies():
    from app.services import pptx_import_service as pptx

    data = _tiny_pptx([
        ("Opening Title", ["First point", "Second point"]),
        ("Second Slide", ["Only bullet"]),
    ])
    slides = pptx.extract_slides(data)
    assert len(slides) == 2
    assert slides[0]["title"] == "Opening Title"
    assert slides[0]["body"] == ["First point", "Second point"]
    assert slides[1]["title"] == "Second Slide"


def test_pptx_extract_rejects_garbage():
    from app.core.exceptions import RevOSError
    from app.services import pptx_import_service as pptx

    with pytest.raises(RevOSError):
        pptx.extract_slides(b"not a zip at all")


@pytest.mark.asyncio
async def test_pptx_deterministic_draft_is_schema_valid(monkeypatch):
    from app.services import ai_service
    from app.services import pptx_import_service as pptx

    monkeypatch.setattr(ai_service, "ai_available", lambda: False)
    slides = pptx.extract_slides(_tiny_pptx([
        ("Big Opener", ["A supporting line"]),
        ("Middle Idea", ["Point one", "Point two"]),
        ("Get In Touch", ["hello@example.com"]),
    ]))
    draft, ai_drafted = await pptx.draft_deck_spec(slides, "acme")
    assert ai_drafted is False
    assert [s["layout"] for s in draft["scenes"]] == ["hero", "statement", "close"]
    deck = svc.validate_deck_spec({**draft, "voice": "x"})
    assert deck.scenes[0].content.headline == "Big Opener"


@pytest.mark.asyncio
async def test_pptx_ai_draft_used_when_valid_and_falls_back_when_not(monkeypatch):
    from app.services import ai_service
    from app.services import pptx_import_service as pptx

    slides = pptx.extract_slides(_tiny_pptx([("Title", ["Body"]), ("End", [])]))
    good_draft = {
        "brandId": "IGNORED — server overrides this", "title": "AI Draft", "aspectRatio": "16:9",
        "voice": "", "scenes": [
            {"id": "s1", "layout": "hero", "variant": "dark",
             "content": {"headline": "AI wrote this."}, "narration": "A-I narration."},
        ],
    }
    import json
    monkeypatch.setattr(ai_service, "ai_available", lambda: True)
    monkeypatch.setattr(ai_service, "generate", lambda **kw: json.dumps(good_draft))
    draft, ai_drafted = await pptx.draft_deck_spec(slides, "acme", style="schematic")
    assert ai_drafted is True
    assert draft["title"] == "AI Draft"
    assert draft["brandId"] == "acme"  # tenant routing never comes from the model
    assert draft["style"] == "schematic"  # the user's choice, not the model's

    # Unparseable AI output → deterministic fallback, not an error.
    monkeypatch.setattr(ai_service, "generate", lambda **kw: "sorry, no json here")
    draft2, ai_drafted2 = await pptx.draft_deck_spec(slides, "acme", style="schematic")
    assert ai_drafted2 is False
    assert draft2["scenes"][0]["layout"] == "hero"
    assert draft2["style"] == "schematic"  # fallback carries the style too


@pytest.mark.asyncio
async def test_import_pptx_endpoint(api, monkeypatch):
    from app.services import ai_service

    _enable(monkeypatch)
    monkeypatch.setattr(ai_service, "ai_available", lambda: False)
    h = await _register_owner(api)
    await api.post("/api/brands", headers=h, json={"name": "Acme", "slug": "acme"})

    r = await api.post(
        "/api/pitch-videos/import-pptx", headers=h,
        files={"file": ("deck.pptx", _tiny_pptx([("Hello", ["World"]), ("Bye", [])]),
                        "application/vnd.openxmlformats-officedocument.presentationml.presentation")},
        data={"brand_slug": "acme"},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["slides_found"] == 2
    assert body["ai_drafted"] is False
    assert body["deck_spec"]["brandId"] == "acme"

    missing = await api.post(
        "/api/pitch-videos/import-pptx", headers=h,
        files={"file": ("deck.pptx", _tiny_pptx([("Hello", [])]), "application/octet-stream")},
        data={"brand_slug": "not-a-brand"},
    )
    assert missing.status_code == 404
