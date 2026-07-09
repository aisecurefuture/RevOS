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

from fastapi import APIRouter, Depends, Request
from fastapi.responses import Response

from app.config import settings
from app.core.exceptions import NotFoundError, RevOSError
from app.deps import DbSession, require_authenticated, require_editor, verify_csrf
from app.models.pitch_video import PitchVideoJobStatus
from app.models.user import AdminUser
from app.schemas.pitch_video import (
    PitchVideoCreateRequest,
    PitchVideoOut,
    StockSpeakersOut,
)
from app.services import pitch_video_service as svc
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


@router.get("/stock-speakers", response_model=StockSpeakersOut)
async def stock_speakers(_user: Annotated[AdminUser, Depends(require_editor)]) -> StockSpeakersOut:
    """Enumerate the built-in XTTS stock voices available on the avatar-worker."""
    _require_enabled()
    backend = get_backend()
    if backend is None or not backend.available or not hasattr(backend, "list_stock_speakers"):
        raise RevOSError("Voice backend is not available on this deployment.", code="backend_unavailable", status_code=502)
    return StockSpeakersOut(speakers=backend.list_stock_speakers())


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
