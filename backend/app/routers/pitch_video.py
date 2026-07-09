"""Pitch Video Studio API (feature-flagged).

Editor+ submits a Deck Spec; the job runs asynchronously (audio generation on
the avatar-worker, then render on the pitch-video-worker); clients poll. The
finished video streams from ``/pitch-videos/{id}/video`` (as an attachment,
matching the Avatar Personas download convention — this codebase has no
signed-URL/CDN pattern) only once the job succeeded.
"""

from __future__ import annotations

import uuid
from typing import Annotated
from urllib.parse import quote

from fastapi import APIRouter, Depends, File, Form, Request, UploadFile
from fastapi.responses import Response
from sqlalchemy import select

from app.config import settings
from app.core.exceptions import NotFoundError, RevOSError
from app.deps import DbSession, require_authenticated, require_editor, verify_csrf
from app.models.brand import Brand
from app.models.pitch_video import PitchVideoJobStatus
from app.models.user import AdminUser
from app.schemas.pitch_video import (
    PitchVideoCreateRequest,
    PitchVideoOut,
    StockSpeakersOut,
)
from app.services import pitch_video_service as svc
from app.services import pptx_import_service
from app.services.avatar.inference import get_backend
from app.services.storage_service import get_storage

router = APIRouter(prefix="/pitch-videos", tags=["pitch-video"])


def _account_id(request: Request) -> uuid.UUID:
    acc = getattr(request.state, "account_id", None)
    if acc is None:
        raise RevOSError("No active account.", code="no_account", status_code=400)
    return acc


def _require_enabled() -> None:
    if not settings.pitch_video_studio_enabled:
        raise RevOSError("Pitch Video Studio is not enabled.", code="feature_disabled", status_code=403)


@router.get("/status")
async def status(_user: Annotated[AdminUser, Depends(require_authenticated)]) -> dict:
    """Lets the frontend show a clean 'not enabled' state instead of a raw 403."""
    return {"enabled": settings.pitch_video_studio_enabled}


# Speaker list is static per XTTS model version — fetch once per process.
_speakers_cache: list[str] | None = None


@router.get("/stock-speakers", response_model=StockSpeakersOut)
async def stock_speakers(_user: Annotated[AdminUser, Depends(require_editor)]) -> StockSpeakersOut:
    """The stock voices available for narration, for the voice dropdown.

    Resolution order: PITCH_VIDEO_VOICES env allowlist → a backend in THIS
    process (dev/tests with the stub) → a round-trip to the avatar-worker
    (the only image with the XTTS venv), cached for the process lifetime.
    Returns an empty list rather than erroring when nothing is reachable —
    the UI degrades to a free-text field.
    """
    global _speakers_cache
    _require_enabled()

    if settings.pitch_video_voices:
        return StockSpeakersOut(speakers=[v.strip() for v in settings.pitch_video_voices.split(",") if v.strip()])
    if _speakers_cache is not None:
        return StockSpeakersOut(speakers=_speakers_cache)

    backend = get_backend()
    if backend is not None and backend.available and hasattr(backend, "list_stock_speakers"):
        _speakers_cache = backend.list_stock_speakers()
        return StockSpeakersOut(speakers=_speakers_cache)

    import asyncio

    def _ask_worker() -> list[str]:
        from app.workers.celery_app import celery_app
        return celery_app.send_task("pitch_video.list_speakers").get(timeout=30)

    try:
        speakers = await asyncio.to_thread(_ask_worker)
    except Exception:  # noqa: BLE001 — worker down/slow: degrade, don't 500
        return StockSpeakersOut(speakers=[])
    if speakers:
        _speakers_cache = speakers
    return StockSpeakersOut(speakers=speakers or [])


@router.post("/import-pptx")
async def import_pptx(
    request: Request, db: DbSession,
    file: UploadFile = File(...),
    brand_slug: str = Form(...),
    user: AdminUser = Depends(require_editor), _: None = Depends(verify_csrf),
) -> dict:
    """Turn an uploaded .pptx into a DRAFT Deck Spec for the studio textarea.

    Always returns a draft for human review — never creates a job directly.
    ``ai_drafted`` tells the UI whether an AI pass shaped it (vs the
    deterministic fallback the user should expect to edit more heavily).
    """
    _require_enabled()
    account_id = _account_id(request)
    brand_result = await db.execute(
        select(Brand).where(
            Brand.slug == brand_slug, Brand.account_id == account_id, Brand.deleted_at.is_(None),
        )
    )
    if brand_result.scalar_one_or_none() is None:
        raise NotFoundError(f"No brand with slug '{brand_slug}' in this account.")

    data = await file.read()
    slides = pptx_import_service.extract_slides(data)
    draft, ai_drafted = await pptx_import_service.draft_deck_spec(slides, brand_slug)
    return {"deck_spec": draft, "ai_drafted": ai_drafted, "slides_found": len(slides)}


@router.get("", response_model=list[PitchVideoOut])
async def list_jobs(
    request: Request, db: DbSession,
    _user: Annotated[AdminUser, Depends(require_authenticated)],
) -> list[PitchVideoOut]:
    _require_enabled()
    jobs = await svc.list_jobs(db, _account_id(request))
    return [PitchVideoOut.from_job(j) for j in jobs]


@router.post("", response_model=PitchVideoOut, status_code=201)
async def create_job(
    body: PitchVideoCreateRequest, request: Request, db: DbSession,
    user: AdminUser = Depends(require_editor), _: None = Depends(verify_csrf),
) -> PitchVideoOut:
    _require_enabled()
    job = await svc.create_job(db, _account_id(request), user, deck_spec_raw=body.deck_spec)
    svc.enqueue_audio_generation(job.id)
    return PitchVideoOut.from_job(job)


@router.get("/{job_id}", response_model=PitchVideoOut)
async def get_job(
    job_id: uuid.UUID, request: Request, db: DbSession,
    _user: Annotated[AdminUser, Depends(require_authenticated)],
) -> PitchVideoOut:
    _require_enabled()
    job = await svc.get_job(db, job_id, _account_id(request))
    return PitchVideoOut.from_job(job)


@router.get("/{job_id}/video")
async def download_video(
    job_id: uuid.UUID, request: Request, db: DbSession,
    _user: Annotated[AdminUser, Depends(require_authenticated)],
) -> Response:
    _require_enabled()
    job = await svc.get_job(db, job_id, _account_id(request))
    if job.status != PitchVideoJobStatus.succeeded or not job.output_path:
        raise NotFoundError("No finished video for this job.")
    data = get_storage().read(job.output_path)
    filename = f"pitch_video_{job_id}.mp4"
    return Response(
        content=data, media_type="video/mp4",
        headers={"Content-Disposition": f"attachment; filename=\"{filename}\"; filename*=UTF-8''{quote(filename)}"},
    )
