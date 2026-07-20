"""Listing Video Studio API (feature-flagged).

Flow: the agent fills the listing form → ``POST /draft-script`` returns a
deterministic voiceover draft (+ Fair Housing warnings) → the agent edits and
approves it → ``POST /listing-videos`` (multipart: details JSON + approved
script + ordered photos) creates the job and kicks off the async pipeline →
clients poll → the finished MP4 downloads from ``/{id}/video``.
"""

from __future__ import annotations

import json
import uuid
from typing import Annotated
from urllib.parse import quote

from fastapi import APIRouter, Depends, File, Form, Request, UploadFile
from fastapi.responses import Response

from app.config import settings
from app.core.exceptions import NotFoundError, RevOSError
from app.deps import DbSession, require_authenticated, require_editor, verify_csrf
from app.models.listing_video import ListingVideoJobStatus
from app.models.user import AdminUser
from app.schemas.listing_video import (
    DraftScriptOut,
    DraftScriptRequest,
    ListingDetails,
    ListingVideoOut,
    MusicTracksOut,
    PersonaVoiceOut,
    VoicesOut,
)
from app.services import listing_video_service as svc
from app.services.storage_service import get_storage

router = APIRouter(prefix="/listing-videos", tags=["listing-video"])


def _account_id(request: Request) -> uuid.UUID:
    acc = getattr(request.state, "account_id", None)
    if acc is None:
        raise RevOSError("No active account.", code="no_account", status_code=400)
    return acc


def _require_enabled() -> None:
    if not settings.listing_video_enabled:
        raise RevOSError("Listing Video Studio is not enabled.", code="feature_disabled", status_code=403)


@router.get("/status")
async def status(_user: Annotated[AdminUser, Depends(require_authenticated)]) -> dict:
    """Lets the frontend show a clean 'not enabled' state instead of a raw 403."""
    return {
        "enabled": settings.listing_video_enabled,
        "min_photos": settings.listing_video_min_photos,
        "max_photos": settings.listing_video_max_photos,
    }


@router.get("/music-tracks", response_model=MusicTracksOut)
async def music_tracks(_user: Annotated[AdminUser, Depends(require_editor)]) -> MusicTracksOut:
    _require_enabled()
    return MusicTracksOut(tracks=svc.music_track_names())


@router.get("/voices", response_model=VoicesOut)
async def voices(
    request: Request, db: DbSession,
    _user: Annotated[AdminUser, Depends(require_editor)],
) -> VoicesOut:
    """Narration options: built-in stock XTTS voices plus this account's
    consented, ready Avatar Persona voices."""
    _require_enabled()
    from app.routers.pitch_video import resolve_stock_speakers

    personas = await svc.list_ready_persona_voices(db, _account_id(request))
    return VoicesOut(
        stock=await resolve_stock_speakers(),
        personas=[PersonaVoiceOut(id=p.id, name=p.name) for p in personas],
    )


@router.post("/draft-script", response_model=DraftScriptOut)
async def draft_script(
    body: DraftScriptRequest,
    user: AdminUser = Depends(require_editor), _: None = Depends(verify_csrf),
) -> DraftScriptOut:
    """Deterministic draft + Fair Housing warnings on the agent's own inputs."""
    _require_enabled()
    script = svc.draft_script(body.details)
    return DraftScriptOut(
        script=script,
        fair_housing_flags=svc.fair_housing_flags(
            script + " " + body.details.hook + " " + " ".join(body.details.features)
        ),
        estimated_spoken_seconds=svc.estimate_spoken_seconds(script),
    )


@router.get("", response_model=list[ListingVideoOut])
async def list_jobs(
    request: Request, db: DbSession,
    _user: Annotated[AdminUser, Depends(require_authenticated)],
) -> list[ListingVideoOut]:
    _require_enabled()
    jobs = await svc.list_jobs(db, _account_id(request))
    return [ListingVideoOut.from_job(j) for j in jobs]


@router.post("", response_model=ListingVideoOut, status_code=201)
async def create_job(
    request: Request, db: DbSession,
    photos: list[UploadFile] = File(...),
    details: str = Form(...),      # ListingDetails as a JSON string (multipart)
    script: str = Form(...),
    brand_slug: str = Form(...),
    music_track: str = Form(""),
    voice_mode: str = Form("stock"),
    speaker_name: str = Form(""),
    persona_identity_id: str = Form(""),
    user: AdminUser = Depends(require_editor), _: None = Depends(verify_csrf),
) -> ListingVideoOut:
    _require_enabled()
    try:
        parsed = ListingDetails.model_validate(json.loads(details))
    except json.JSONDecodeError as exc:
        raise RevOSError("details must be a JSON object.", code="bad_details", status_code=400) from exc

    persona_uuid: uuid.UUID | None = None
    if persona_identity_id:
        try:
            persona_uuid = uuid.UUID(persona_identity_id)
        except ValueError as exc:
            raise RevOSError("persona_identity_id must be a UUID.", code="bad_persona_id", status_code=400) from exc

    photo_payloads: list[tuple[str, bytes]] = []
    for p in photos:
        photo_payloads.append((p.content_type or "", await p.read()))

    job = await svc.create_job(
        db, _account_id(request), user,
        brand_slug=brand_slug, details=parsed, script=script,
        music_track=music_track, photos=photo_payloads,
        voice_mode=voice_mode, speaker_name=speaker_name,
        persona_identity_id=persona_uuid,
    )
    svc.enqueue_audio_generation(job.id)
    return ListingVideoOut.from_job(job)


@router.get("/{job_id}", response_model=ListingVideoOut)
async def get_job(
    job_id: uuid.UUID, request: Request, db: DbSession,
    _user: Annotated[AdminUser, Depends(require_authenticated)],
) -> ListingVideoOut:
    _require_enabled()
    job = await svc.get_job(db, job_id, _account_id(request))
    return ListingVideoOut.from_job(job)


@router.get("/{job_id}/video")
async def download_video(
    job_id: uuid.UUID, request: Request, db: DbSession,
    _user: Annotated[AdminUser, Depends(require_authenticated)],
) -> Response:
    _require_enabled()
    job = await svc.get_job(db, job_id, _account_id(request))
    if job.status != ListingVideoJobStatus.succeeded or not job.output_path:
        raise NotFoundError("No finished video for this job.")
    data = get_storage().read(job.output_path)
    filename = f"listing_video_{job_id}.mp4"
    return Response(
        content=data, media_type="video/mp4",
        headers={"Content-Disposition": f"attachment; filename=\"{filename}\"; filename*=UTF-8''{quote(filename)}"},
    )
