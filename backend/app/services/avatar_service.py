"""Avatar video generation orchestration (Phase 3 M3).

The main app calls ``create_job`` (validates the persona, estimates wait time,
records a queued job) then enqueues a Celery task on the ``avatar`` queue. The
avatar-worker runs ``run_generation``: read the persona's consented media from
storage, drive the inference backend (voice → lip-sync), store the result, and
mark the job. Everything is scoped so a persona whose consent was revoked can
never be used, even if a job for it was queued earlier.
"""

from __future__ import annotations

import asyncio
import logging
import tempfile
import uuid
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.core.exceptions import ConflictError, NotFoundError, RevOSError
from app.models.avatar_job import AvatarJobStatus, AvatarVideoJob
from app.models.base import utcnow
from app.models.persona_identity import PersonaIdentity
from app.models.user import AdminUser
from app.services import persona_identity_service
from app.services.avatar.inference import get_backend
from app.services.storage_service import get_storage

logger = logging.getLogger("revos.avatar")

ALLOWED_DURATIONS = (7, 15, 30, 45, 60, 90, 120)
_MAX_SCRIPT_CHARS = 5000


def estimate_seconds(target_seconds: int) -> int:
    """Wall-clock estimate for a video of ~target_seconds, from the measured
    per-frame CPU cost."""
    return int(target_seconds * settings.avatar_est_fps * settings.avatar_est_seconds_per_frame)


# ---------------------------------------------------------------------------
# CRUD
# ---------------------------------------------------------------------------

async def get_job(db: AsyncSession, job_id: uuid.UUID, account_id: uuid.UUID) -> AvatarVideoJob:
    result = await db.execute(
        select(AvatarVideoJob).where(
            AvatarVideoJob.id == job_id,
            AvatarVideoJob.account_id == account_id,
            AvatarVideoJob.deleted_at.is_(None),
        )
    )
    job = result.scalar_one_or_none()
    if job is None:
        raise NotFoundError("Avatar job not found.")
    return job


async def list_jobs(
    db: AsyncSession, account_id: uuid.UUID, persona_identity_id: uuid.UUID | None = None
) -> list[AvatarVideoJob]:
    filters = [AvatarVideoJob.account_id == account_id, AvatarVideoJob.deleted_at.is_(None)]
    if persona_identity_id is not None:
        filters.append(AvatarVideoJob.persona_identity_id == persona_identity_id)
    result = await db.execute(
        select(AvatarVideoJob).where(*filters).order_by(AvatarVideoJob.created_at.desc())
    )
    return list(result.scalars().all())


async def create_job(
    db: AsyncSession, account_id: uuid.UUID, user: AdminUser,
    *, persona_identity_id: uuid.UUID, script: str, target_seconds: int,
) -> AvatarVideoJob:
    if target_seconds not in ALLOWED_DURATIONS:
        raise RevOSError(
            f"Duration must be one of {ALLOWED_DURATIONS} seconds.",
            code="invalid_duration", status_code=400,
        )
    script = script.strip()
    if not script:
        raise RevOSError("Script is required.", code="empty_script", status_code=400)
    if len(script) > _MAX_SCRIPT_CHARS:
        raise RevOSError("Script is too long.", code="script_too_long", status_code=400)

    # The persona must belong to this account and be consent-ready.
    identity = await persona_identity_service.get_identity(db, persona_identity_id, account_id)
    if not persona_identity_service.is_usable_for_generation(identity):
        raise ConflictError(
            "This persona isn't ready for generation. It needs a training video, a "
            "voice sample, and an active consent record."
        )
    if not identity.training_video_path or not identity.voice_sample_path:
        raise ConflictError("This persona is missing a training video or voice sample.")

    job = AvatarVideoJob(
        account_id=account_id,
        persona_identity_id=persona_identity_id,
        brand_id=identity.brand_id,
        script=script,
        target_seconds=target_seconds,
        estimated_seconds=estimate_seconds(target_seconds),
        status=AvatarJobStatus.queued,
        created_by=user.id,
    )
    db.add(job)
    await db.flush()
    await db.refresh(job)
    return job


def enqueue(job_id: uuid.UUID) -> None:
    """Dispatch the generation task to the dedicated avatar queue (best-effort;
    a failure to enqueue leaves the job 'queued' for a later sweep/retry)."""
    try:
        from app.workers.celery_app import celery_app
        celery_app.send_task("avatar.generate", args=[str(job_id)])
    except Exception:  # noqa: BLE001 — broker hiccup must not fail the request
        logger.exception("Failed to enqueue avatar job %s", job_id)


# ---------------------------------------------------------------------------
# Generation (runs in the avatar worker)
# ---------------------------------------------------------------------------

def _fail(job: AvatarVideoJob, message: str) -> None:
    job.status = AvatarJobStatus.failed
    job.error = message[:2000]
    job.finished_at = utcnow()


async def run_generation(db: AsyncSession, job: AvatarVideoJob) -> None:
    if job.status not in (AvatarJobStatus.queued, AvatarJobStatus.processing):
        return  # already terminal — idempotent against duplicate deliveries

    backend = get_backend()
    if backend is None or not backend.available:
        _fail(job, "Avatar generation backend is not configured on this worker.")
        db.add(job)
        await db.flush()
        return

    identity = await db.get(PersonaIdentity, job.persona_identity_id)
    if identity is None or not persona_identity_service.is_usable_for_generation(identity):
        _fail(job, "Persona is not usable for generation (consent revoked or media missing).")
        db.add(job)
        await db.flush()
        return
    if not identity.training_video_path or not identity.voice_sample_path:
        _fail(job, "Persona is missing a training video or voice sample.")
        db.add(job)
        await db.flush()
        return

    job.status = AvatarJobStatus.processing
    job.started_at = utcnow()
    db.add(job)
    await db.flush()

    storage = get_storage()
    try:
        with tempfile.TemporaryDirectory() as tmp:
            face = Path(tmp) / "face.mp4"
            voice = Path(tmp) / "voice.wav"
            audio = Path(tmp) / "audio.wav"
            output = Path(tmp) / "output.mp4"
            face.write_bytes(storage.read(identity.training_video_path))
            voice.write_bytes(storage.read(identity.voice_sample_path))

            await asyncio.to_thread(
                backend.generate_voice,
                script=job.script, voice_sample_path=str(voice), out_path=str(audio),
            )
            await asyncio.to_thread(
                backend.lip_sync,
                face_video_path=str(face), audio_path=str(audio), out_path=str(output),
            )

            key = f"avatars/{job.id}/output.mp4"
            storage.save(key, output.read_bytes())
            job.output_path = key
            job.status = AvatarJobStatus.succeeded
    except Exception as exc:  # noqa: BLE001 — surface any failure on the job row
        logger.exception("Avatar job %s failed", job.id)
        job.status = AvatarJobStatus.failed
        job.error = str(exc)[:2000]

    job.finished_at = utcnow()
    db.add(job)
    await db.flush()
