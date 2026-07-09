"""Pitch Video Studio (feature-flagged) — Deck Spec -> narrated MP4.

Two stages, chained across two worker images via Celery:

  1. ``run_audio_generation`` (queue ``avatar``, runs in the EXISTING
     avatar-worker image) — reuses the exact same
     ``avatar.inference.InferenceBackend.generate_voice`` Avatar Personas
     calls; no new TTS vendor, no changes needed to that image. Voice is a
     built-in XTTS-v2 stock speaker (no cloning, no consent surface — there's
     no persona to clone for a brand narrator). Caches audio by
     hash(narration text + voice), and measures each clip's real duration via
     ffprobe to build the ``scene_manifest`` frame timing Remotion needs.

  2. ``run_render`` (queue ``pitch_video``, runs in the NEW pitch-video-worker
     image — Node + Remotion + Chromium, zero Python ML deps) — materializes
     the manifest's audio into a local render dir (works for either storage
     backend) and shells out to ``npx remotion render`` with a props JSON
     built from the manifest + the brand's design tokens.

v1 scope: voice is always ``stock`` (a built-in XTTS speaker). The DB model
already carries a ``clone`` mode + ``persona_identity_id`` for a brand that
wants to reuse one of its own consented personas as narrator, but resolving
that from a Deck Spec isn't wired up yet — deliberately deferred, see the
Phase 0 discovery notes.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import math
import shutil
import subprocess
import tempfile
import uuid
from pathlib import Path

from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.core.exceptions import NotFoundError, RevOSError
from app.core.tenancy import set_active_account
from app.models.base import utcnow
from app.models.brand import Brand
from app.models.pitch_video import PitchVideoJob, PitchVideoJobStatus, PitchVideoVoiceMode
from app.models.user import AdminUser
from app.schemas.pitch_video import DeckSpec
from app.services.avatar.inference import get_backend
from app.services.storage_service import get_storage

logger = logging.getLogger("revos.pitch_video")

FPS = 30
_ESTIMATED_CHARS_PER_SECOND_AUDIO_GEN = 8.0   # rough XTTS CPU-gen wall-clock heuristic
_ESTIMATED_RENDER_SECONDS_PER_VIDEO_SECOND = 3.0  # rough headless-Chromium CPU render heuristic


# ---------------------------------------------------------------------------
# Pure helpers (unit-testable without any I/O)
# ---------------------------------------------------------------------------

def cache_key(text: str, voice_key: str) -> str:
    """Deterministic cache key for one scene's narration audio."""
    return hashlib.sha256(f"{voice_key}:{text}".encode()).hexdigest()


def seconds_to_frames(seconds: float, fps: int = FPS) -> int:
    """Round up so a clip is never truncated mid-word; at least 1 frame."""
    return max(1, math.ceil(seconds * fps))


def validate_deck_spec(raw: dict) -> DeckSpec:
    try:
        deck = DeckSpec.model_validate(raw)
    except ValidationError as exc:
        raise RevOSError(
            f"Invalid Deck Spec: {exc.errors()[0]['msg']}", code="invalid_deck_spec", status_code=400,
        ) from exc
    if len(deck.scenes) > settings.pitch_video_max_scenes:
        raise RevOSError(
            f"Deck has {len(deck.scenes)} scenes; max is {settings.pitch_video_max_scenes}.",
            code="too_many_scenes", status_code=400,
        )
    return deck


def _estimate_seconds(deck: DeckSpec) -> int:
    total_chars = sum(len(s.narration) for s in deck.scenes)
    audio_gen = total_chars / _ESTIMATED_CHARS_PER_SECOND_AUDIO_GEN
    # Rough spoken-duration guess (150wpm ≈ 8 chars/word ≈ 20 chars/sec) drives
    # the render-time estimate; real timing comes from measured audio later.
    spoken_seconds = total_chars / 20.0
    render = spoken_seconds * _ESTIMATED_RENDER_SECONDS_PER_VIDEO_SECOND
    return int(audio_gen + render)


def _probe_duration_seconds(path: str) -> float:
    if not shutil.which("ffprobe"):
        raise RevOSError("ffprobe is not available on this worker.", code="ffprobe_missing", status_code=502)
    result = subprocess.run(  # noqa: S603
        ["ffprobe", "-v", "quiet", "-print_format", "json", "-show_format", path],  # noqa: S607
        capture_output=True, text=True, timeout=30, check=False,
    )
    try:
        info = json.loads(result.stdout or "{}")
        return float(info["format"]["duration"])
    except (KeyError, ValueError, TypeError) as exc:
        raise RevOSError(f"Could not measure audio duration for {path}.", code="probe_failed", status_code=502) from exc


# ---------------------------------------------------------------------------
# CRUD
# ---------------------------------------------------------------------------

async def get_job(db: AsyncSession, job_id: uuid.UUID, account_id: uuid.UUID) -> PitchVideoJob:
    result = await db.execute(
        select(PitchVideoJob).where(
            PitchVideoJob.id == job_id,
            PitchVideoJob.account_id == account_id,
            PitchVideoJob.deleted_at.is_(None),
        )
    )
    job = result.scalar_one_or_none()
    if job is None:
        raise NotFoundError("Pitch video job not found.")
    return job


async def list_jobs(db: AsyncSession, account_id: uuid.UUID) -> list[PitchVideoJob]:
    result = await db.execute(
        select(PitchVideoJob).where(
            PitchVideoJob.account_id == account_id, PitchVideoJob.deleted_at.is_(None),
        ).order_by(PitchVideoJob.created_at.desc())
    )
    return list(result.scalars().all())


async def create_job(
    db: AsyncSession, account_id: uuid.UUID, user: AdminUser, *, deck_spec_raw: dict,
) -> PitchVideoJob:
    if not settings.pitch_video_studio_enabled:
        raise RevOSError("Pitch Video Studio is not enabled.", code="feature_disabled", status_code=403)

    deck = validate_deck_spec(deck_spec_raw)

    brand_result = await db.execute(
        select(Brand).where(
            Brand.slug == deck.brand_id, Brand.account_id == account_id, Brand.deleted_at.is_(None),
        )
    )
    brand = brand_result.scalar_one_or_none()
    if brand is None:
        raise NotFoundError(f"No brand with slug '{deck.brand_id}' in this account.")

    speaker_name = deck.voice or settings.pitch_video_default_voice
    if not speaker_name:
        raise RevOSError(
            "No voice specified in the Deck Spec and no PITCH_VIDEO_DEFAULT_VOICE is configured.",
            code="no_voice_configured", status_code=400,
        )

    job = PitchVideoJob(
        account_id=account_id,
        brand_id=brand.id,
        title=deck.title,
        aspect_ratio=deck.aspect_ratio,
        voice_mode=PitchVideoVoiceMode.stock,
        speaker_name=speaker_name,
        deck_spec=deck.model_dump(by_alias=True),
        status=PitchVideoJobStatus.queued,
        estimated_seconds=_estimate_seconds(deck),
        created_by=user.id,
    )
    db.add(job)
    await db.flush()
    await db.refresh(job)
    return job


def enqueue_audio_generation(job_id: uuid.UUID) -> None:
    try:
        from app.workers.celery_app import celery_app
        celery_app.send_task("pitch_video.generate_audio", args=[str(job_id)])
    except Exception:  # noqa: BLE001 — broker hiccup must not fail the request
        logger.exception("Failed to enqueue pitch video audio generation %s", job_id)


def _enqueue_render(job_id: uuid.UUID) -> None:
    try:
        from app.workers.celery_app import celery_app
        celery_app.send_task("pitch_video.render", args=[str(job_id)])
    except Exception:  # noqa: BLE001
        logger.exception("Failed to enqueue pitch video render %s", job_id)


def _fail(job: PitchVideoJob, message: str) -> None:
    job.status = PitchVideoJobStatus.failed
    job.error = message[:2000]
    job.finished_at = utcnow()


# ---------------------------------------------------------------------------
# Stage 1 — audio generation (runs in avatar-worker)
# ---------------------------------------------------------------------------

async def run_audio_generation(db: AsyncSession, job: PitchVideoJob) -> None:
    if job.status != PitchVideoJobStatus.queued:
        return  # already terminal/in-flight — idempotent against redelivery

    backend = get_backend()
    if backend is None or not backend.available:
        _fail(job, "Avatar generation backend is not configured on this worker.")
        db.add(job)
        await db.flush()
        return
    if job.voice_mode != PitchVideoVoiceMode.stock or not job.speaker_name:
        _fail(job, "Only voice_mode=stock is supported in this version.")
        db.add(job)
        await db.flush()
        return

    set_active_account(job.account_id)
    job.status = PitchVideoJobStatus.generating_audio
    job.started_at = utcnow()
    db.add(job)
    await db.flush()

    storage = get_storage()
    deck = DeckSpec.model_validate(job.deck_spec)

    try:
        manifest: list[dict] = []
        frame_cursor = 0
        for i, scene in enumerate(deck.scenes):
            job.progress_note = f"Generating narration for scene {i + 1}/{len(deck.scenes)}…"
            db.add(job)
            await db.flush()

            key = cache_key(scene.narration, job.speaker_name)
            cache_path = f"pitch-videos/tts-cache/{key}.wav"
            with tempfile.TemporaryDirectory() as tmp:
                local_wav = Path(tmp) / "audio.wav"
                if storage.exists(cache_path):
                    local_wav.write_bytes(storage.read(cache_path))
                else:
                    await _generate_scene_audio(backend, scene.narration, job.speaker_name, str(local_wav))
                    storage.save(cache_path, local_wav.read_bytes())
                duration = _probe_duration_seconds(str(local_wav))

            frame_count = seconds_to_frames(duration)
            manifest.append({
                "scene_id": scene.id, "audio_path": cache_path,
                "duration_seconds": duration,
                "frame_start": frame_cursor, "frame_count": frame_count,
            })
            frame_cursor += frame_count

        job.scene_manifest = manifest
        job.status = PitchVideoJobStatus.rendering
        job.progress_note = "Rendering video…"
        db.add(job)
        await db.flush()
        _enqueue_render(job.id)
    except Exception as exc:  # noqa: BLE001 — surface any failure on the job row
        logger.exception("Pitch video audio generation failed for job %s", job.id)
        _fail(job, str(exc))
        db.add(job)
        await db.flush()


async def _generate_scene_audio(backend, narration: str, speaker_name: str, out_path: str) -> None:
    await asyncio.to_thread(
        backend.generate_voice, script=narration, out_path=out_path, speaker_name=speaker_name,
    )


# ---------------------------------------------------------------------------
# Stage 2 — render (runs in pitch-video-worker)
# ---------------------------------------------------------------------------

_ASPECT_DIMENSIONS = {"16:9": (1920, 1080), "9:16": (1080, 1920), "1:1": (1080, 1080)}


async def run_render(db: AsyncSession, job: PitchVideoJob) -> None:
    if job.status != PitchVideoJobStatus.rendering:
        return  # idempotent against redelivery

    remotion_dir = settings.pitch_video_remotion_dir
    if not remotion_dir or not Path(remotion_dir).exists():
        _fail(job, "Remotion project is not configured on this worker.")
        db.add(job)
        await db.flush()
        return

    set_active_account(job.account_id)
    brand = await db.get(Brand, job.brand_id)
    if brand is None:
        _fail(job, "Brand no longer exists.")
        db.add(job)
        await db.flush()
        return

    storage = get_storage()
    deck = DeckSpec.model_validate(job.deck_spec)
    width, height = _ASPECT_DIMENSIONS[job.aspect_ratio]

    try:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            manifest_by_id = {m["scene_id"]: m for m in job.scene_manifest}
            scenes_props = []
            for scene in deck.scenes:
                m = manifest_by_id[scene.id]
                local_audio = tmp_path / f"{scene.id}.wav"
                local_audio.write_bytes(storage.read(m["audio_path"]))
                scenes_props.append({
                    "id": scene.id, "layout": scene.layout, "variant": scene.variant,
                    "content": scene.content.model_dump(),
                    # Filename only — Remotion resolves this via staticFile()
                    # against REMOTION_PUBLIC_DIR (set below), not a raw path.
                    "audioPath": local_audio.name,
                    "frameStart": m["frame_start"], "frameCount": m["frame_count"],
                })

            props = {
                "title": deck.title,
                "fps": FPS, "width": width, "height": height,
                "designTokens": brand.design_tokens,
                "scenes": scenes_props,
            }
            props_path = tmp_path / "props.json"
            props_path.write_text(json.dumps(props), encoding="utf-8")

            out_path = tmp_path / "output.mp4"
            _run_remotion_render(remotion_dir, str(props_path), str(out_path), public_dir=str(tmp_path))

            if not out_path.exists():
                raise RevOSError("Render produced no output file.", code="render_no_output", status_code=502)

            key = f"pitch-videos/{job.id}/output.mp4"
            storage.save(key, out_path.read_bytes())
            job.output_path = key
            job.status = PitchVideoJobStatus.succeeded
            job.progress_note = None
    except Exception as exc:  # noqa: BLE001
        logger.exception("Pitch video render failed for job %s", job.id)
        _fail(job, str(exc))

    job.finished_at = utcnow()
    db.add(job)
    await db.flush()


def _run_remotion_render(remotion_dir: str, props_path: str, out_path: str, *, public_dir: str) -> None:
    import os

    cmd = [
        settings.pitch_video_node_bin, "remotion", "render", "src/index.ts", "PitchVideo", out_path,
        f"--props={props_path}",
        f"--concurrency={settings.pitch_video_render_concurrency}",
    ]
    logger.info("pitch_video[render]: %s", " ".join(cmd))
    try:
        proc = subprocess.run(
            cmd, cwd=remotion_dir, capture_output=True, text=True,
            timeout=settings.pitch_video_render_timeout_seconds,
            env={**os.environ, "REMOTION_PUBLIC_DIR": public_dir},
        )
    except subprocess.TimeoutExpired as exc:
        raise RevOSError(
            f"Render timed out after {settings.pitch_video_render_timeout_seconds}s.",
            code="render_timeout", status_code=502,
        ) from exc
    if proc.returncode != 0:
        tail = (proc.stderr or proc.stdout or "")[-2000:]
        logger.error("pitch_video[render] failed (%s): %s", proc.returncode, tail)
        raise RevOSError(f"Render failed: {tail}", code="render_failed", status_code=502)
