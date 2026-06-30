"""Sequence + step CRUD (the authoring side; runtime is in sequence_engine)."""

from __future__ import annotations

import uuid

from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from app.core.sanitize import sanitize_html
from app.core.text import clean_text, slugify
from app.models.sequence import ABTest, Sequence, SequenceStep
from app.schemas.sequence import SequenceCreate, SequenceUpdate, StepCreate, StepUpdate
from app.services.crud import get_active, list_active, unique_slug


async def list_sequences(
    db: AsyncSession, *, brand_id: uuid.UUID | None = None, limit: int = 50, offset: int = 0
) -> list[Sequence]:
    filters = [Sequence.brand_id == brand_id] if brand_id else []
    return await list_active(db, Sequence, filters=filters, limit=limit, offset=offset)


async def get_sequence_or_404(db: AsyncSession, sequence_id: uuid.UUID) -> Sequence:
    return await get_active(db, Sequence, sequence_id)


async def create_sequence(db: AsyncSession, body: SequenceCreate) -> Sequence:
    base = slugify(body.slug or body.name)
    slug = await unique_slug(db, Sequence, base, brand_id=body.brand_id)
    sequence = Sequence(
        brand_id=body.brand_id, name=clean_text(body.name) or body.name, slug=slug,
        sequence_type=body.sequence_type, description=clean_text(body.description),
        trigger=body.trigger, stop_on_goal=body.stop_on_goal, goal_event=body.goal_event,
        stop_on_reply=body.stop_on_reply, require_approval=body.require_approval,
    )
    db.add(sequence)
    await db.flush()
    await db.refresh(sequence)
    return sequence


async def update_sequence(db: AsyncSession, sequence: Sequence, body: SequenceUpdate) -> Sequence:
    data = body.model_dump(exclude_unset=True)
    for field in ("name", "description"):
        if field in data and data[field] is not None:
            data[field] = clean_text(data[field])
    for key, value in data.items():
        setattr(sequence, key, value)
    db.add(sequence)
    await db.flush()
    await db.refresh(sequence)
    return sequence


async def list_steps(db: AsyncSession, sequence_id: uuid.UUID) -> list[SequenceStep]:
    result = await db.execute(
        select(SequenceStep).where(
            SequenceStep.sequence_id == sequence_id, SequenceStep.deleted_at.is_(None)
        ).order_by(SequenceStep.order_index)
    )
    return list(result.scalars().all())


async def create_step(db: AsyncSession, sequence: Sequence, body: StepCreate) -> SequenceStep:
    step = SequenceStep(
        sequence_id=sequence.id, name=clean_text(body.name) or "",
        order_index=body.order_index, delay_minutes=body.delay_minutes,
        subject=body.subject,
        html_body=sanitize_html(body.html_body) if body.html_body else None,
        text_body=body.text_body, template_id=body.template_id,
        condition=body.condition, require_approval=body.require_approval,
    )
    db.add(step)
    await db.flush()

    if body.ab_variants:
        db.add(ABTest(
            brand_id=sequence.brand_id, sequence_step_id=step.id,
            name=f"{step.name or 'Step'} subject test", metric="open",
            variants=[v.model_dump() for v in body.ab_variants], status="active",
        ))
        await db.flush()

    await db.refresh(step)
    return step


async def get_step_or_404(db: AsyncSession, step_id: uuid.UUID) -> SequenceStep:
    return await get_active(db, SequenceStep, step_id)


async def update_step(db: AsyncSession, step: SequenceStep, body: StepUpdate) -> SequenceStep:
    data = body.model_dump(exclude_unset=True)
    if "html_body" in data and data["html_body"] is not None:
        data["html_body"] = sanitize_html(data["html_body"])
    if "name" in data and data["name"] is not None:
        data["name"] = clean_text(data["name"])
    for key, value in data.items():
        setattr(step, key, value)
    db.add(step)
    await db.flush()
    await db.refresh(step)
    return step
