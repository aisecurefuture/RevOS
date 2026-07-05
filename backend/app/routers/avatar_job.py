"""Avatar video generation — jobs API (Phase 3 M3).

Editor+ creates and views jobs. Generation runs asynchronously on the avatar
worker; clients poll the job. The finished video streams from
``/avatar/jobs/{id}/video`` (as an attachment) only once the job succeeded.
"""

from __future__ import annotations

import uuid
from typing import Annotated
from urllib.parse import quote

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import Response

from app.core.exceptions import NotFoundError, RevOSError
from app.deps import DbSession, require_authenticated, require_editor, verify_csrf
from app.models.avatar_job import AvatarJobStatus
from app.models.user import AdminUser
from app.schemas.avatar_job import AvatarJobCreate, AvatarJobOut
from app.services import avatar_service
from app.services.storage_service import get_storage

router = APIRouter(prefix="/avatar", tags=["avatar"])


def _account_id(request: Request) -> uuid.UUID:
    acc = getattr(request.state, "account_id", None)
    if acc is None:
        raise RevOSError("No active account.", code="no_account", status_code=400)
    return acc


@router.get("/durations")
async def durations(_user: Annotated[AdminUser, Depends(require_authenticated)]) -> dict:
    """The allowed durations, each with an honest wait-time estimate so the UI
    can set expectations before a job is even created."""
    return {
        "durations": [
            {"seconds": d, "estimated_seconds": avatar_service.estimate_seconds(d)}
            for d in avatar_service.ALLOWED_DURATIONS
        ]
    }


@router.get("/jobs", response_model=list[AvatarJobOut])
async def list_jobs(
    request: Request, db: DbSession,
    _user: Annotated[AdminUser, Depends(require_authenticated)],
    persona_identity_id: uuid.UUID | None = Query(default=None),
) -> list[AvatarJobOut]:
    jobs = await avatar_service.list_jobs(db, _account_id(request), persona_identity_id)
    return [AvatarJobOut.from_job(j) for j in jobs]


@router.post("/jobs", response_model=AvatarJobOut, status_code=201)
async def create_job(
    body: AvatarJobCreate, request: Request, db: DbSession,
    user: AdminUser = Depends(require_editor), _: None = Depends(verify_csrf),
) -> AvatarJobOut:
    job = await avatar_service.create_job(
        db, _account_id(request), user,
        persona_identity_id=body.persona_identity_id,
        script=body.script, target_seconds=body.target_seconds,
    )
    avatar_service.enqueue(job.id)
    return AvatarJobOut.from_job(job)


@router.get("/jobs/{job_id}", response_model=AvatarJobOut)
async def get_job(
    job_id: uuid.UUID, request: Request, db: DbSession,
    _user: Annotated[AdminUser, Depends(require_authenticated)],
) -> AvatarJobOut:
    job = await avatar_service.get_job(db, job_id, _account_id(request))
    return AvatarJobOut.from_job(job)


@router.get("/jobs/{job_id}/video")
async def download_video(
    job_id: uuid.UUID, request: Request, db: DbSession,
    _user: Annotated[AdminUser, Depends(require_authenticated)],
) -> Response:
    job = await avatar_service.get_job(db, job_id, _account_id(request))
    if job.status != AvatarJobStatus.succeeded or not job.output_path:
        raise NotFoundError("No finished video for this job.")
    data = get_storage().read(job.output_path)
    filename = f"avatar_{job_id}.mp4"
    return Response(
        content=data, media_type="video/mp4",
        headers={"Content-Disposition": f"attachment; filename=\"{filename}\"; filename*=UTF-8''{quote(filename)}"},
    )
