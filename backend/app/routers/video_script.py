"""Viral video script engine — API (Phase 3 M4).

Editor+. Generates brand-grounded, duration-sized, gate-checked spoken scripts
for avatar videos; scripts are reviewable/editable before being handed to a
(slow) avatar generation job.
"""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request, Response

from app.core.exceptions import RevOSError
from app.deps import DbSession, require_authenticated, require_editor, verify_csrf
from app.models.user import AdminUser
from app.schemas.video_script import (
    ScriptGenerateRequest,
    ScriptUpdateRequest,
    VideoScriptOut,
)
from app.services import script_engine_service as svc

router = APIRouter(prefix="/scripts", tags=["video-scripts"])


def _account_id(request: Request) -> uuid.UUID:
    acc = getattr(request.state, "account_id", None)
    if acc is None:
        raise RevOSError("No active account.", code="no_account", status_code=400)
    return acc


@router.get("", response_model=list[VideoScriptOut])
async def list_scripts(
    request: Request, db: DbSession,
    _user: Annotated[AdminUser, Depends(require_authenticated)],
    brand_id: uuid.UUID | None = Query(default=None),
    persona_identity_id: uuid.UUID | None = Query(default=None),
) -> list[VideoScriptOut]:
    scripts = await svc.list_scripts(db, _account_id(request), brand_id, persona_identity_id)
    return [VideoScriptOut.model_validate(s) for s in scripts]


@router.post("/generate", response_model=VideoScriptOut, status_code=201)
async def generate_script(
    body: ScriptGenerateRequest, request: Request, db: DbSession,
    user: AdminUser = Depends(require_editor), _: None = Depends(verify_csrf),
) -> VideoScriptOut:
    script = await svc.generate_script(
        db, _account_id(request), user,
        brand_id=body.brand_id, target_seconds=body.target_seconds,
        persona_identity_id=body.persona_identity_id, angle=body.angle,
    )
    return VideoScriptOut.model_validate(script)


@router.get("/{script_id}", response_model=VideoScriptOut)
async def get_script(
    script_id: uuid.UUID, request: Request, db: DbSession,
    _user: Annotated[AdminUser, Depends(require_authenticated)],
) -> VideoScriptOut:
    script = await svc.get_script(db, script_id, _account_id(request))
    return VideoScriptOut.model_validate(script)


@router.patch("/{script_id}", response_model=VideoScriptOut)
async def update_script(
    script_id: uuid.UUID, body: ScriptUpdateRequest, request: Request, db: DbSession,
    user: AdminUser = Depends(require_editor), _: None = Depends(verify_csrf),
) -> VideoScriptOut:
    script = await svc.update_script(db, script_id, _account_id(request), body.script)
    return VideoScriptOut.model_validate(script)


@router.delete("/{script_id}", status_code=204)
async def delete_script(
    script_id: uuid.UUID, request: Request, db: DbSession,
    user: AdminUser = Depends(require_editor), _: None = Depends(verify_csrf),
) -> Response:
    await svc.delete_script(db, script_id, _account_id(request))
    return Response(status_code=204)
