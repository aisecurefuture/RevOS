"""Listing Video Studio — listing details + photos -> ~30s vertical MP4.

Rides the exact same two-stage pipeline as Pitch Video Studio:

  1. ``listing_video.generate_audio`` (queue ``avatar``) — XTTS stock-voice
     narration of the agent-approved script, cached by hash(text+voice),
     measured with ffprobe, producing the frame timeline for Remotion.
  2. ``listing_video.render`` (queue ``pitch_video``) — materializes photos +
     narration + the licensed music bed into a temp public dir and shells out
     to ``npx remotion render`` for the ListingVideo composition (1080x1920).

Script drafting is DETERMINISTIC (template over the form fields) — no LLM in
the loop for v1, so it is fast, free, testable, and can never hallucinate a
detail the agent didn't type. The agent reviews/edits the draft in the UI.

Fair Housing guard: US law (Fair Housing Act) prohibits steering/preference
language in housing ads ("perfect for families", "safe neighborhood",
"exclusive community", religious/demographic references…). ``fair_housing_flags``
screens BOTH the drafted inputs (warning at draft time) and the final
submitted script (hard reject at job creation) — protecting the agent and us.

Music: only tracks from ``settings.listing_video_music_dir`` (a directory of
LICENSED royalty-free beds baked into the render-worker image). MusicGen's
released weights are CC-BY-NC — generating our own music commercially awaits
a properly-licensed model on the GPU box (see deploy/listing-video/music/).
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
import subprocess
import tempfile
import uuid
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.core.exceptions import NotFoundError, RevOSError
from app.core.tenancy import set_active_account
from app.models.base import utcnow
from app.models.brand import Brand
from app.models.listing_video import ListingVideoJob, ListingVideoJobStatus
from app.models.user import AdminUser
from app.schemas.listing_video import ListingDetails
from app.services.avatar.inference import get_backend
from app.services.pitch_video_service import (
    _probe_duration_seconds,
    cache_key,
    seconds_to_frames,
)
from app.services.storage_service import get_storage

logger = logging.getLogger("revos.listing_video")

FPS = 30
# Fixed bookend cards around the photo reel (frames @ 30fps).
INTRO_FRAMES = 75    # 2.5s address/price title card
OUTRO_FRAMES = 105   # 3.5s agent/brokerage + CTA card
MIN_FRAMES_PER_PHOTO = 45          # never flash a photo for under 1.5s
_ESTIMATED_CHARS_PER_SECOND_AUDIO_GEN = 8.0
_ESTIMATED_RENDER_SECONDS_PER_VIDEO_SECOND = 3.0
_SPOKEN_CHARS_PER_SECOND = 20.0    # ~150wpm heuristic for draft-time estimates

_ALLOWED_PHOTO_TYPES = {"image/jpeg": ".jpg", "image/png": ".png", "image/webp": ".webp"}


# ---------------------------------------------------------------------------
# Fair Housing guard (pure, unit-testable)
# ---------------------------------------------------------------------------

# Steering / preference / demographic phrases prohibited or risky under the
# Fair Housing Act in ad copy. Matched case-insensitively on word boundaries.
# Deliberately focused on describing PEOPLE rather than the PROPERTY —
# "family room" is fine, "perfect for families" is not.
_FAIR_HOUSING_PATTERNS: tuple[str, ...] = (
    r"perfect for (young )?famil(y|ies)",
    r"ideal for (young )?famil(y|ies)",
    r"family[- ]friendly",
    r"great for kids",
    r"no kids",
    r"no children",
    r"adults? only",
    r"perfect for (a )?(young )?(couple|professional|bachelor|retiree)s?",
    r"ideal for (a )?(young )?(couple|professional|bachelor|retiree)s?",
    r"bachelor pad",
    r"empty[- ]nesters?",
    r"safe neighborhood",
    r"low[- ]crime",
    r"exclusive (neighborhood|community|area|enclave)",
    r"desirable (ethnic|cultural)",
    r"(christian|jewish|muslim|hindu|catholic) (community|neighborhood|area)",
    r"near(by)? (churches|synagogues|mosques|temples)",
    r"walking distance (to|of) (church|synagogue|mosque|temple)",
    r"no section 8",
    r"section 8 not",
    r"english[- ]speaking",
    r"integrated neighborhood",
    r"traditional neighborhood",
    r"(hispanic|latino|asian|black|white|indian) (neighborhood|community|area)",
    r"able[- ]bodied",
    r"no wheelchairs?",
    r"not suitable for (the )?(disabled|handicapped)",
)
_FAIR_HOUSING_RES = tuple(re.compile(rf"\b{p}\b", re.IGNORECASE) for p in _FAIR_HOUSING_PATTERNS)


def fair_housing_flags(text: str) -> list[str]:
    """Return the distinct prohibited/risky phrases found in ``text``."""
    found: list[str] = []
    for rx in _FAIR_HOUSING_RES:
        m = rx.search(text)
        if m and m.group(0).lower() not in (f.lower() for f in found):
            found.append(m.group(0))
    return found


# ---------------------------------------------------------------------------
# Script drafting (pure, deterministic)
# ---------------------------------------------------------------------------

def _fmt_num(n: float) -> str:
    return str(int(n)) if float(n).is_integer() else str(n)


def draft_script(details: ListingDetails) -> str:
    """Deterministic voiceover draft from the form fields.

    Describes the PROPERTY, never the buyer — the Fair Housing guard also
    screens the agent's own hook/features inputs at draft time. Target length
    lands near 30s spoken (~600 chars) for a 10-photo reel.
    """
    parts: list[str] = []

    intro_bits: list[str] = []
    if details.listing_type and details.listing_type.lower() != "for sale":
        intro_bits.append(details.listing_type)
    location = f"{details.street} in {details.city}, {details.state}"
    parts.append(
        f"{' — '.join(intro_bits) + ': ' if intro_bits else ''}Welcome to {location}."
    )

    if details.hook.strip():
        parts.append(details.hook.strip().rstrip(".") + ".")

    fact_bits: list[str] = []
    if details.beds:
        fact_bits.append(f"{_fmt_num(details.beds)} bedrooms")
    if details.baths:
        fact_bits.append(f"{_fmt_num(details.baths)} bathrooms")
    if details.sqft:
        fact_bits.append(f"{details.sqft:,} square feet")
    if details.lot.strip():
        fact_bits.append(details.lot.strip())
    if fact_bits:
        if len(fact_bits) > 1:
            facts = ", ".join(fact_bits[:-1]) + f", and {fact_bits[-1]}"
        else:
            facts = fact_bits[0]
        parts.append(f"This home offers {facts}.")

    if details.features:
        feats = [f.rstrip(".") for f in details.features[:5]]
        if len(feats) > 1:
            feat_line = ", ".join(feats[:-1]) + f", and {feats[-1]}"
        else:
            feat_line = feats[0]
        parts.append(f"Highlights include {feat_line}.")

    if details.year_built:
        parts.append(f"Built in {details.year_built}.")

    if details.price_text.strip():
        parts.append(f"Offered at {details.price_text.strip()}.")

    close = "Schedule your private showing today"
    if details.agent_name.strip():
        close += f" with {details.agent_name.strip()}"
        if details.brokerage.strip():
            close += f" at {details.brokerage.strip()}"
    parts.append(close + ".")

    return " ".join(parts)


def estimate_spoken_seconds(script: str) -> int:
    return max(1, round(len(script) / _SPOKEN_CHARS_PER_SECOND))


# ---------------------------------------------------------------------------
# Timeline math (pure, unit-testable)
# ---------------------------------------------------------------------------

def build_timeline(photo_count: int, narration_frames: int) -> dict:
    """Distribute the video's frames across intro card, photo reel, outro.

    The video is exactly as long as the narration plus a short tail, but the
    photo reel never drops below MIN_FRAMES_PER_PHOTO per photo — with a
    short narration the video simply runs a little longer than the audio.
    """
    if photo_count < 1:
        raise ValueError("photo_count must be >= 1")
    tail = FPS // 2  # half-second breath after the voice ends
    total = INTRO_FRAMES + OUTRO_FRAMES + max(
        narration_frames + tail - INTRO_FRAMES - OUTRO_FRAMES,
        photo_count * MIN_FRAMES_PER_PHOTO,
    )
    reel_frames = total - INTRO_FRAMES - OUTRO_FRAMES
    base = reel_frames // photo_count
    remainder = reel_frames % photo_count
    photos = []
    cursor = INTRO_FRAMES
    for i in range(photo_count):
        count = base + (1 if i < remainder else 0)
        photos.append({"index": i, "frame_start": cursor, "frame_count": count})
        cursor += count
    return {
        "fps": FPS,
        "total_frames": total,
        "intro_frames": INTRO_FRAMES,
        "outro_frames": OUTRO_FRAMES,
        "photos": photos,
    }


def _estimate_seconds(script: str) -> int:
    audio_gen = len(script) / _ESTIMATED_CHARS_PER_SECOND_AUDIO_GEN
    spoken = len(script) / _SPOKEN_CHARS_PER_SECOND
    render = max(spoken, 30.0) * _ESTIMATED_RENDER_SECONDS_PER_VIDEO_SECOND
    return int(audio_gen + render)


def music_track_names() -> list[str]:
    return [t.strip() for t in settings.listing_video_music_tracks.split(",") if t.strip()]


# ---------------------------------------------------------------------------
# CRUD
# ---------------------------------------------------------------------------

async def get_job(db: AsyncSession, job_id: uuid.UUID, account_id: uuid.UUID) -> ListingVideoJob:
    result = await db.execute(
        select(ListingVideoJob).where(
            ListingVideoJob.id == job_id,
            ListingVideoJob.account_id == account_id,
            ListingVideoJob.deleted_at.is_(None),
        )
    )
    job = result.scalar_one_or_none()
    if job is None:
        raise NotFoundError("Listing video job not found.")
    return job


async def list_jobs(db: AsyncSession, account_id: uuid.UUID) -> list[ListingVideoJob]:
    result = await db.execute(
        select(ListingVideoJob).where(
            ListingVideoJob.account_id == account_id, ListingVideoJob.deleted_at.is_(None),
        ).order_by(ListingVideoJob.created_at.desc())
    )
    return list(result.scalars().all())


async def create_job(
    db: AsyncSession,
    account_id: uuid.UUID,
    user: AdminUser,
    *,
    brand_slug: str,
    details: ListingDetails,
    script: str,
    music_track: str,
    photos: list[tuple[str, bytes]],  # (content_type, data), in render order
) -> ListingVideoJob:
    if not settings.listing_video_enabled:
        raise RevOSError("Listing Video Studio is not enabled.", code="feature_disabled", status_code=403)

    script = script.strip()
    if not script:
        raise RevOSError("The voiceover script is empty.", code="empty_script", status_code=400)
    flags = fair_housing_flags(script)
    if flags:
        raise RevOSError(
            "The script contains language that may violate the Fair Housing Act: "
            + "; ".join(f"“{f}”" for f in flags)
            + ". Describe the property, not the buyer, and resubmit.",
            code="fair_housing_violation", status_code=400,
        )

    n = len(photos)
    if n < settings.listing_video_min_photos:
        raise RevOSError(
            f"At least {settings.listing_video_min_photos} photos are required (got {n}).",
            code="too_few_photos", status_code=400,
        )
    if n > settings.listing_video_max_photos:
        raise RevOSError(
            f"At most {settings.listing_video_max_photos} photos are allowed (got {n}).",
            code="too_many_photos", status_code=400,
        )
    for i, (ctype, data) in enumerate(photos):
        if ctype not in _ALLOWED_PHOTO_TYPES:
            raise RevOSError(
                f"Photo {i + 1}: unsupported type {ctype!r} (use JPEG, PNG, or WebP).",
                code="bad_photo_type", status_code=400,
            )
        if len(data) > settings.listing_video_max_photo_bytes:
            raise RevOSError(
                f"Photo {i + 1} exceeds {settings.listing_video_max_photo_bytes // (1024 * 1024)}MB.",
                code="photo_too_large", status_code=400,
            )

    if music_track and music_track not in music_track_names():
        raise RevOSError(f"Unknown music track {music_track!r}.", code="bad_music_track", status_code=400)

    brand_result = await db.execute(
        select(Brand).where(
            Brand.slug == brand_slug, Brand.account_id == account_id, Brand.deleted_at.is_(None),
        )
    )
    brand = brand_result.scalar_one_or_none()
    if brand is None:
        raise NotFoundError(f"No brand with slug '{brand_slug}' in this account.")

    speaker = settings.listing_video_default_voice or settings.pitch_video_default_voice
    if not speaker:
        raise RevOSError(
            "No narration voice configured (set LISTING_VIDEO_DEFAULT_VOICE).",
            code="no_voice_configured", status_code=400,
        )

    job = ListingVideoJob(
        account_id=account_id,
        brand_id=brand.id,
        address=details.address_line,
        details=details.model_dump(),
        script=script,
        music_track=music_track,
        speaker_name=speaker,
        status=ListingVideoJobStatus.queued,
        estimated_seconds=_estimate_seconds(script),
        created_by=user.id,
    )
    db.add(job)
    await db.flush()

    storage = get_storage()
    paths: list[str] = []
    for i, (ctype, data) in enumerate(photos):
        ext = _ALLOWED_PHOTO_TYPES[ctype]
        key = f"listing-videos/{job.id}/photos/{i:02d}{ext}"
        storage.save(key, data)
        paths.append(key)
    job.photo_paths = paths
    db.add(job)
    await db.flush()
    await db.refresh(job)
    return job


def enqueue_audio_generation(job_id: uuid.UUID) -> None:
    try:
        from app.workers.celery_app import celery_app
        celery_app.send_task("listing_video.generate_audio", args=[str(job_id)])
    except Exception:  # noqa: BLE001 — broker hiccup must not fail the request
        logger.exception("Failed to enqueue listing video audio generation %s", job_id)


def _enqueue_render(job_id: uuid.UUID) -> None:
    try:
        from app.workers.celery_app import celery_app
        celery_app.send_task("listing_video.render", args=[str(job_id)])
    except Exception:  # noqa: BLE001
        logger.exception("Failed to enqueue listing video render %s", job_id)


def _fail(job: ListingVideoJob, message: str) -> None:
    job.status = ListingVideoJobStatus.failed
    job.error = message[:2000]
    job.finished_at = utcnow()


# ---------------------------------------------------------------------------
# Stage 1 — narration audio (runs in avatar-worker)
# ---------------------------------------------------------------------------

async def run_audio_generation(db: AsyncSession, job: ListingVideoJob) -> None:
    if job.status != ListingVideoJobStatus.queued:
        return  # idempotent against redelivery

    backend = get_backend()
    if backend is None or not backend.available:
        _fail(job, "Voice generation backend is not configured on this worker.")
        db.add(job)
        await db.flush()
        return

    set_active_account(job.account_id)
    job.status = ListingVideoJobStatus.generating_audio
    job.started_at = utcnow()
    job.progress_note = "Generating voiceover…"
    db.add(job)
    await db.flush()

    storage = get_storage()
    try:
        key = cache_key(job.script, job.speaker_name)
        cache_path = f"listing-videos/tts-cache/{key}.wav"
        with tempfile.TemporaryDirectory() as tmp:
            local_wav = Path(tmp) / "narration.wav"
            if storage.exists(cache_path):
                local_wav.write_bytes(storage.read(cache_path))
            else:
                await asyncio.to_thread(
                    backend.generate_voice,
                    script=job.script, out_path=str(local_wav), speaker_name=job.speaker_name,
                )
                storage.save(cache_path, local_wav.read_bytes())
            duration = _probe_duration_seconds(str(local_wav))

        narration_frames = seconds_to_frames(duration, FPS)
        timeline = build_timeline(len(job.photo_paths), narration_frames)
        job.render_manifest = {
            "narration_path": cache_path,
            "narration_seconds": duration,
            "narration_frames": narration_frames,
            "timeline": timeline,
        }
        job.status = ListingVideoJobStatus.rendering
        job.progress_note = "Rendering video…"
        db.add(job)
        await db.flush()
        _enqueue_render(job.id)
    except Exception as exc:  # noqa: BLE001 — surface any failure on the job row
        logger.exception("Listing video audio generation failed for job %s", job.id)
        _fail(job, str(exc))
        db.add(job)
        await db.flush()


# ---------------------------------------------------------------------------
# Stage 2 — render (runs in pitch-video-worker)
# ---------------------------------------------------------------------------

WIDTH, HEIGHT = 1080, 1920  # vertical 9:16 for TikTok / Instagram Reels


async def run_render(db: AsyncSession, job: ListingVideoJob) -> None:
    if job.status != ListingVideoJobStatus.rendering:
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
    try:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)

            photo_files: list[str] = []
            for i, key in enumerate(job.photo_paths):
                local = tmp_path / f"photo_{i:02d}{Path(key).suffix}"
                local.write_bytes(storage.read(key))
                photo_files.append(local.name)

            manifest = job.render_manifest
            narration_local = tmp_path / "narration.wav"
            narration_local.write_bytes(storage.read(manifest["narration_path"]))

            music_file: str | None = None
            if job.music_track:
                music_src = Path(settings.listing_video_music_dir) / job.music_track
                if music_src.exists():
                    music_local = tmp_path / f"music{music_src.suffix}"
                    music_local.write_bytes(music_src.read_bytes())
                    music_file = music_local.name
                else:
                    logger.warning(
                        "Music track %s missing on worker; rendering without music.", job.music_track,
                    )

            details = job.details
            props = {
                "fps": FPS, "width": WIDTH, "height": HEIGHT,
                "address": job.address,
                "priceText": details.get("price_text", ""),
                "listingType": details.get("listing_type", "For Sale"),
                "beds": details.get("beds"),
                "baths": details.get("baths"),
                "sqft": details.get("sqft"),
                "features": details.get("features", []),
                "agentName": details.get("agent_name", ""),
                "agentPhone": details.get("agent_phone", ""),
                "brokerage": details.get("brokerage", ""),
                "designTokens": brand.design_tokens,
                "photos": photo_files,
                "narrationPath": narration_local.name,
                "musicPath": music_file,
                "musicVolume": settings.listing_video_music_volume,
                "timeline": manifest["timeline"],
            }
            props_path = tmp_path / "props.json"
            props_path.write_text(json.dumps(props), encoding="utf-8")

            out_path = tmp_path / "output.mp4"
            _run_remotion_render(remotion_dir, str(props_path), str(out_path), public_dir=str(tmp_path))

            if not out_path.exists():
                raise RevOSError("Render produced no output file.", code="render_no_output", status_code=502)

            out_key = f"listing-videos/{job.id}/output.mp4"
            storage.save(out_key, out_path.read_bytes())
            job.output_path = out_key
            job.status = ListingVideoJobStatus.succeeded
            job.progress_note = None
    except Exception as exc:  # noqa: BLE001
        logger.exception("Listing video render failed for job %s", job.id)
        _fail(job, str(exc))

    job.finished_at = utcnow()
    db.add(job)
    await db.flush()


def _run_remotion_render(remotion_dir: str, props_path: str, out_path: str, *, public_dir: str) -> None:
    import os

    cmd = [
        settings.pitch_video_node_bin, "remotion", "render", "src/index.ts", "ListingVideo", out_path,
        f"--props={props_path}",
        f"--concurrency={settings.pitch_video_render_concurrency}",
    ]
    logger.info("listing_video[render]: %s", " ".join(cmd))
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
        logger.error("listing_video[render] failed (%s): %s", proc.returncode, tail)
        raise RevOSError(f"Render failed: {tail}", code="render_failed", status_code=502)
