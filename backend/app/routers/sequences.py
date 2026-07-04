"""Sequence authoring + runtime control: steps, enroll, activate, tick, goals."""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request

from app.core.audit import write_audit
from app.core.exceptions import RevOSError
from app.deps import (
    DbSession,
    require_admin,
    require_authenticated,
    require_editor,
    verify_csrf,
)
from app.models.lead import Lead
from app.models.sequence import Enrollment, Sequence, SequenceStatus, SequenceStep
from app.models.user import AdminUser
from app.schemas.common import Message
from app.schemas.sequence import (
    EnrollmentOut,
    EnrollRequest,
    GoalEvent,
    SequenceCreate,
    SequenceDetailOut,
    SequenceOut,
    SequenceUpdate,
    StepCreate,
    StepOut,
    StepUpdate,
    TickResult,
)
from app.services import sequence_engine, sequence_service
from app.services.crud import get_active, list_active, soft_delete

router = APIRouter(prefix="/sequences", tags=["sequences"])


# --- Sequences --------------------------------------------------------------
@router.get("", response_model=list[SequenceOut])
async def list_sequences(
    db: DbSession,
    _user: Annotated[AdminUser, Depends(require_authenticated)],
    brand_id: uuid.UUID | None = None,
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
) -> list[Sequence]:
    return await sequence_service.list_sequences(db, brand_id=brand_id, limit=limit, offset=offset)


@router.post("", response_model=SequenceOut, status_code=201)
async def create_sequence(
    body: SequenceCreate,
    request: Request,
    db: DbSession,
    user: Annotated[AdminUser, Depends(require_editor)],
    _: None = Depends(verify_csrf),
) -> Sequence:
    sequence = await sequence_service.create_sequence(db, body)
    await write_audit(db, action="sequence.create", user_id=user.id,
                      entity_type="sequence", entity_id=str(sequence.id), request=request)
    return sequence


@router.post("/tick", response_model=TickResult)
async def run_tick(
    request: Request,
    db: DbSession,
    user: Annotated[AdminUser, Depends(require_admin)],
    _: None = Depends(verify_csrf),
) -> TickResult:
    """Advance all due enrollments now (ops/manual trigger; also runs on a beat)."""
    stats = await sequence_engine.tick_due(db)
    await write_audit(db, action="sequence.tick", user_id=user.id, request=request, meta=stats)
    return TickResult(**stats)


@router.post("/goal", response_model=Message)
async def record_goal(
    body: GoalEvent,
    db: DbSession,
    _user: Annotated[AdminUser, Depends(require_admin)],
    _: None = Depends(verify_csrf),
) -> Message:
    count = await sequence_engine.record_goal(db, lead_id=body.lead_id, event_name=body.event_name)
    return Message(status="ok", detail=f"{count} enrollment(s) marked goal-met")


@router.get("/{sequence_id}", response_model=SequenceDetailOut)
async def get_sequence(
    sequence_id: uuid.UUID,
    db: DbSession,
    _user: Annotated[AdminUser, Depends(require_authenticated)],
) -> SequenceDetailOut:
    sequence = await sequence_service.get_sequence_or_404(db, sequence_id)
    detail = SequenceDetailOut.model_validate(sequence)
    detail.steps = [StepOut.model_validate(s) for s in
                    await sequence_service.list_steps(db, sequence_id)]
    return detail


@router.patch("/{sequence_id}", response_model=SequenceOut)
async def update_sequence(
    sequence_id: uuid.UUID,
    body: SequenceUpdate,
    request: Request,
    db: DbSession,
    user: Annotated[AdminUser, Depends(require_editor)],
    _: None = Depends(verify_csrf),
) -> Sequence:
    sequence = await sequence_service.get_sequence_or_404(db, sequence_id)
    sequence = await sequence_service.update_sequence(db, sequence, body)
    await write_audit(db, action="sequence.update", user_id=user.id,
                      entity_type="sequence", entity_id=str(sequence_id), request=request)
    return sequence


async def _set_status(db, sequence_id, status, user, request, action):
    sequence = await sequence_service.get_sequence_or_404(db, sequence_id)
    sequence.status = status
    db.add(sequence)
    await db.flush()
    await db.refresh(sequence)
    await write_audit(db, action=action, user_id=user.id,
                      entity_type="sequence", entity_id=str(sequence_id), request=request)
    return sequence


@router.post("/{sequence_id}/activate", response_model=SequenceOut)
async def activate(
    sequence_id: uuid.UUID, request: Request, db: DbSession,
    user: Annotated[AdminUser, Depends(require_editor)], _: None = Depends(verify_csrf),
) -> Sequence:
    return await _set_status(db, sequence_id, SequenceStatus.active, user, request,
                             "sequence.activate")


@router.post("/{sequence_id}/pause", response_model=SequenceOut)
async def pause(
    sequence_id: uuid.UUID, request: Request, db: DbSession,
    user: Annotated[AdminUser, Depends(require_editor)], _: None = Depends(verify_csrf),
) -> Sequence:
    return await _set_status(db, sequence_id, SequenceStatus.paused, user, request,
                             "sequence.pause")


# --- Steps ------------------------------------------------------------------
@router.post("/{sequence_id}/steps", response_model=StepOut, status_code=201)
async def create_step(
    sequence_id: uuid.UUID,
    body: StepCreate,
    request: Request,
    db: DbSession,
    user: Annotated[AdminUser, Depends(require_editor)],
    _: None = Depends(verify_csrf),
) -> SequenceStep:
    sequence = await sequence_service.get_sequence_or_404(db, sequence_id)
    step = await sequence_service.create_step(db, sequence, body)
    await write_audit(db, action="sequence.step_create", user_id=user.id,
                      entity_type="sequence_step", entity_id=str(step.id), request=request)
    return step


@router.patch("/steps/{step_id}", response_model=StepOut)
async def update_step(
    step_id: uuid.UUID,
    body: StepUpdate,
    request: Request,
    db: DbSession,
    user: Annotated[AdminUser, Depends(require_editor)],
    _: None = Depends(verify_csrf),
) -> SequenceStep:
    step = await sequence_service.get_step_or_404(db, step_id)
    step = await sequence_service.update_step(db, step, body)
    await write_audit(db, action="sequence.step_update", user_id=user.id,
                      entity_type="sequence_step", entity_id=str(step_id), request=request)
    return step


@router.delete("/steps/{step_id}", response_model=Message)
async def delete_step(
    step_id: uuid.UUID,
    request: Request,
    db: DbSession,
    user: Annotated[AdminUser, Depends(require_editor)],
    _: None = Depends(verify_csrf),
) -> Message:
    step = await sequence_service.get_step_or_404(db, step_id)
    await soft_delete(db, step)
    await write_audit(db, action="sequence.step_delete", user_id=user.id,
                      entity_type="sequence_step", entity_id=str(step_id), request=request)
    return Message(status="deleted")


# --- Enrollments ------------------------------------------------------------
@router.post("/{sequence_id}/enroll", response_model=EnrollmentOut, status_code=201)
async def enroll(
    sequence_id: uuid.UUID,
    body: EnrollRequest,
    request: Request,
    db: DbSession,
    user: Annotated[AdminUser, Depends(require_editor)],
    _: None = Depends(verify_csrf),
) -> Enrollment:
    sequence = await sequence_service.get_sequence_or_404(db, sequence_id)
    lead = await get_active(db, Lead, body.lead_id)
    enrollment = await sequence_engine.enroll(db, sequence, lead.id)
    if enrollment is None:
        raise RevOSError("Could not enroll: sequence inactive, has no steps, or lead "
                         "already enrolled.")
    await write_audit(db, action="sequence.enroll", user_id=user.id,
                      entity_type="enrollment", entity_id=str(enrollment.id), request=request)
    return enrollment


@router.get("/{sequence_id}/enrollments", response_model=list[EnrollmentOut])
async def list_enrollments(
    sequence_id: uuid.UUID,
    db: DbSession,
    _user: Annotated[AdminUser, Depends(require_authenticated)],
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
) -> list[Enrollment]:
    return await list_active(db, Enrollment, filters=[Enrollment.sequence_id == sequence_id],
                             limit=limit, offset=offset)


@router.post("/enrollments/{enrollment_id}/pause", response_model=EnrollmentOut)
async def pause_enrollment(
    enrollment_id: uuid.UUID, request: Request, db: DbSession,
    user: Annotated[AdminUser, Depends(require_editor)], _: None = Depends(verify_csrf),
) -> Enrollment:
    enrollment = await get_active(db, Enrollment, enrollment_id)
    return await sequence_engine.set_enrollment_state(db, enrollment, paused=True)


@router.post("/enrollments/{enrollment_id}/resume", response_model=EnrollmentOut)
async def resume_enrollment(
    enrollment_id: uuid.UUID, request: Request, db: DbSession,
    user: Annotated[AdminUser, Depends(require_editor)], _: None = Depends(verify_csrf),
) -> Enrollment:
    enrollment = await get_active(db, Enrollment, enrollment_id)
    return await sequence_engine.set_enrollment_state(db, enrollment, paused=False)
