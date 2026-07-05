"""Render pipeline (Phase 3 M6) — captions + per-platform framing on a
finished avatar video, then hand it to a SocialPost so it flows through the
same approval gate as every other post.

Nothing new to trust here: per-platform cropping reuses media_service's
existing ffmpeg rendering (VIDEO_SPECS), and publishing reuses
social_connection_service.submit_for_approval. This module is just the seam
connecting a finished AvatarVideoJob to that pipeline. Caption burn-in is a
nice-to-have — if ffmpeg is missing or the render fails, we fall back to the
uncaptioned video rather than blocking the publish.
"""

from __future__ import annotations

import logging
import subprocess
import tempfile
import uuid
from pathlib import Path

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ConflictError
from app.core.tenancy import set_active_account
from app.models.avatar_job import AvatarJobStatus, AvatarVideoJob
from app.models.social import SocialPlatform
from app.models.user import AdminUser
from app.services import media_service, social_connection_service, social_service
from app.services.storage_service import get_storage

logger = logging.getLogger("revos.avatar_render")

_MAX_CAPTION_CHARS = 70  # per on-screen line — keep it readable on a phone
_CAPTION_WORDS_PER_CHUNK = 6


def _escape_drawtext(text: str) -> str:
    return (
        text.replace("\\", "\\\\")
        .replace(":", "\\:")
        .replace("'", "’")  # smart-quote instead of escaping — simpler & safe
        .replace("%", "\\%")
    )


def _caption_chunks(script: str, duration_seconds: int) -> list[tuple[float, float, str]]:
    """Split the script into short on-screen chunks spread evenly across the
    video's duration (mirrors the word-count duration model in
    script_engine_service: words ≈ duration × 2.5wps)."""
    words = script.split()
    if not words:
        return []
    chunks = [
        " ".join(words[i:i + _CAPTION_WORDS_PER_CHUNK])[:_MAX_CAPTION_CHARS]
        for i in range(0, len(words), _CAPTION_WORDS_PER_CHUNK)
    ]
    span = duration_seconds / len(chunks)
    return [(round(i * span, 2), round((i + 1) * span, 2), c) for i, c in enumerate(chunks)]


def burn_captions(video_bytes: bytes, script: str, duration_seconds: int) -> bytes | None:
    """Burn simple centered captions via ffmpeg drawtext. Returns None (caller
    falls back to the uncaptioned video) if ffmpeg is unavailable or the
    render fails."""
    if not media_service.ffmpeg_available():
        return None
    chunks = _caption_chunks(script, duration_seconds)
    if not chunks:
        return None

    vf = ",".join(
        f"drawtext=text='{_escape_drawtext(text)}':fontcolor=white:fontsize=48:"
        "box=1:boxcolor=black@0.55:boxborderw=16:x=(w-text_w)/2:y=h-th-80:"
        f"enable='between(t,{start},{end})'"
        for start, end, text in chunks
    )

    with tempfile.NamedTemporaryFile(suffix=".mp4") as src, \
            tempfile.NamedTemporaryFile(suffix=".mp4") as dst:
        src.write(video_bytes)
        src.flush()
        result = subprocess.run(  # noqa: S603
            ["ffmpeg", "-y", "-i", src.name, "-vf", vf, "-c:a", "copy",  # noqa: S607
             "-movflags", "+faststart", dst.name],
            capture_output=True, timeout=600, check=False,
        )
        if result.returncode != 0:
            logger.warning(
                "Caption burn-in failed for a %ss video: %s",
                duration_seconds, result.stderr.decode(errors="replace")[-500:],
            )
            return None
        return Path(dst.name).read_bytes()


def _default_caption(job: AvatarVideoJob) -> str:
    first_line = job.script.strip().splitlines()[0] if job.script.strip() else ""
    return first_line[:280] or "New video"


async def publish_avatar_job(
    db: AsyncSession, job: AvatarVideoJob, account_id: uuid.UUID, user: AdminUser,
    *, platform: SocialPlatform, caption: str | None = None, burn_captions_on: bool = True,
):
    """Render the finished avatar video for one platform, attach it to a new
    SocialPost, and submit it for approval."""
    if job.status != AvatarJobStatus.succeeded or not job.output_path:
        raise ConflictError("This avatar job has no finished video yet.")
    if job.brand_id is None:
        raise ConflictError("This avatar job has no brand to publish under.")

    set_active_account(account_id)
    storage = get_storage()
    video_bytes = storage.read(job.output_path)

    if burn_captions_on:
        captioned = burn_captions(video_bytes, job.script, job.target_seconds)
        if captioned is not None:
            video_bytes = captioned

    asset = await media_service.create_asset(
        db, brand_id=job.brand_id, uploader_id=user.id,
        filename=f"avatar_{job.id}.mp4", data=video_bytes, mime="video/mp4",
    )
    # Renders the platform's aspect ratio via the same VIDEO_SPECS used for
    # uploaded media. Platforms with no video spec (e.g. LinkedIn, Threads)
    # fall back to the original framing — still a valid, publishable file.
    variants = await media_service.process_asset(db, asset, platforms=[str(platform)], enhance=False)
    media_key = variants[0].path if variants else asset.original_path

    post = await social_service.create_post(db, {
        "brand_id": job.brand_id,
        "platform": platform,
        "caption": caption if caption is not None else _default_caption(job),
        "media_urls": [media_key],
    })
    approval = await social_connection_service.submit_for_approval(db, post.id, account_id, user)
    return post, approval
