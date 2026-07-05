"""Persona identity — likeness, voice, consent (Phase 3 M2).

Editor+ manages identity and uploads media. Consent grant/revoke is admin+ —
it's the compliance-critical action that unlocks (or permanently blocks) using
a real person's likeness in generation.
"""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, File, Form, Query, Request, Response, UploadFile

from app.core.exceptions import RevOSError
from app.deps import DbSession, require_admin, require_authenticated, require_editor, verify_csrf
from app.models.user import AdminUser
from app.schemas.persona_identity import (
    ConsentGrantRequest,
    ConsentOut,
    PersonaIdentityCreate,
    PersonaIdentityOut,
    PersonaIdentityUpdate,
)
from app.services import persona_identity_service as svc

router = APIRouter(prefix="/personas", tags=["persona-identity"])


def _account_id(request: Request) -> uuid.UUID:
    acc = getattr(request.state, "account_id", None)
    if acc is None:
        raise RevOSError("No active account.", code="no_account", status_code=400)
    return acc


@router.get("", response_model=list[PersonaIdentityOut])
async def list_identities(
    request: Request, db: DbSession,
    _user: Annotated[AdminUser, Depends(require_authenticated)],
    brand_id: uuid.UUID | None = None,
) -> list[PersonaIdentityOut]:
    identities = await svc.list_identities(db, _account_id(request), brand_id)
    return [PersonaIdentityOut.model_validate(i) for i in identities]


@router.post("", response_model=PersonaIdentityOut, status_code=201)
async def create_identity(
    body: PersonaIdentityCreate, request: Request, db: DbSession,
    user: AdminUser = Depends(require_editor), _: None = Depends(verify_csrf),
) -> PersonaIdentityOut:
    identity = await svc.create_identity(db, _account_id(request), user, body.model_dump())
    return PersonaIdentityOut.model_validate(identity)


@router.get("/{identity_id}", response_model=PersonaIdentityOut)
async def get_identity(
    identity_id: uuid.UUID, request: Request, db: DbSession,
    _user: Annotated[AdminUser, Depends(require_authenticated)],
) -> PersonaIdentityOut:
    identity = await svc.get_identity(db, identity_id, _account_id(request))
    return PersonaIdentityOut.model_validate(identity)


@router.patch("/{identity_id}", response_model=PersonaIdentityOut)
async def update_identity(
    identity_id: uuid.UUID, body: PersonaIdentityUpdate, request: Request, db: DbSession,
    user: AdminUser = Depends(require_editor), _: None = Depends(verify_csrf),
) -> PersonaIdentityOut:
    identity = await svc.update_identity(
        db, identity_id, _account_id(request), body.model_dump(exclude_unset=True),
    )
    return PersonaIdentityOut.model_validate(identity)


@router.delete("/{identity_id}", status_code=204)
async def delete_identity(
    identity_id: uuid.UUID, request: Request, db: DbSession,
    user: AdminUser = Depends(require_editor), _: None = Depends(verify_csrf),
) -> Response:
    await svc.delete_identity(db, identity_id, _account_id(request))
    return Response(status_code=204)


# --- Media uploads -----------------------------------------------------------

@router.post("/{identity_id}/training-video", response_model=PersonaIdentityOut)
async def upload_training_video(
    identity_id: uuid.UUID, request: Request, db: DbSession,
    file: Annotated[UploadFile, File()],
    user: AdminUser = Depends(require_editor), _: None = Depends(verify_csrf),
) -> PersonaIdentityOut:
    data = await file.read()
    identity = await svc.upload_training_video(
        db, identity_id, _account_id(request), file.filename or "video.mp4", data, file.content_type,
    )
    return PersonaIdentityOut.model_validate(identity)


@router.post("/{identity_id}/voice-sample", response_model=PersonaIdentityOut)
async def upload_voice_sample(
    identity_id: uuid.UUID, request: Request, db: DbSession,
    file: Annotated[UploadFile, File()],
    user: AdminUser = Depends(require_editor), _: None = Depends(verify_csrf),
) -> PersonaIdentityOut:
    data = await file.read()
    identity = await svc.upload_voice_sample(
        db, identity_id, _account_id(request), file.filename or "voice.mp3", data, file.content_type,
    )
    return PersonaIdentityOut.model_validate(identity)


@router.post("/{identity_id}/reference-images", response_model=PersonaIdentityOut)
async def upload_reference_image(
    identity_id: uuid.UUID, request: Request, db: DbSession,
    file: Annotated[UploadFile, File()],
    user: AdminUser = Depends(require_editor), _: None = Depends(verify_csrf),
) -> PersonaIdentityOut:
    data = await file.read()
    identity = await svc.upload_reference_image(
        db, identity_id, _account_id(request), file.filename or "image.jpg", data, file.content_type,
    )
    return PersonaIdentityOut.model_validate(identity)


@router.delete("/{identity_id}/reference-images", response_model=PersonaIdentityOut)
async def remove_reference_image(
    identity_id: uuid.UUID, request: Request, db: DbSession,
    path: str = Query(...),
    user: AdminUser = Depends(require_editor), _: None = Depends(verify_csrf),
) -> PersonaIdentityOut:
    identity = await svc.remove_reference_image(db, identity_id, _account_id(request), path)
    return PersonaIdentityOut.model_validate(identity)


# --- Consent ------------------------------------------------------------------

@router.get("/{identity_id}/consents", response_model=list[ConsentOut])
async def list_consents(
    identity_id: uuid.UUID, request: Request, db: DbSession,
    _user: Annotated[AdminUser, Depends(require_authenticated)],
) -> list[ConsentOut]:
    await svc.get_identity(db, identity_id, _account_id(request))  # 404s if cross-account
    return [ConsentOut.model_validate(c) for c in await svc.list_consents(db, identity_id)]


@router.post("/{identity_id}/consent", response_model=ConsentOut, status_code=201)
async def grant_consent(
    identity_id: uuid.UUID, body: ConsentGrantRequest, request: Request, db: DbSession,
    user: AdminUser = Depends(require_admin), _: None = Depends(verify_csrf),
) -> ConsentOut:
    consent = await svc.grant_consent(
        db, identity_id, _account_id(request), user,
        subject_name=body.subject_name, subject_email=str(body.subject_email),
        consent_statement=body.consent_statement,
    )
    return ConsentOut.model_validate(consent)


@router.post("/{identity_id}/consent/revoke", response_model=PersonaIdentityOut)
async def revoke_consent(
    identity_id: uuid.UUID, request: Request, db: DbSession,
    user: AdminUser = Depends(require_admin), _: None = Depends(verify_csrf),
) -> PersonaIdentityOut:
    identity = await svc.revoke_consent(db, identity_id, _account_id(request), user)
    return PersonaIdentityOut.model_validate(identity)
