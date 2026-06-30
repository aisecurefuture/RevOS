"""Sequence runtime: enrollment, the tick, goals, pause/resume, A/B, approvals.

The tick advances every due enrollment by one step: it checks stop conditions
(unsubscribed / goal met / paused sequence), optionally routes the step through
the approval gate, otherwise renders + sends via the Module 7 sender (which
re-enforces consent/suppression) and schedules the next step after its delay.
"""

from __future__ import annotations

import hashlib
import uuid
from datetime import timedelta

from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from app.models.approval import ApprovalAction
from app.models.base import utcnow
from app.models.brand import Brand
from app.models.email import EmailCategory, EmailMessage, EmailStatus
from app.models.lead import ConsentStatus, Lead
from app.models.sequence import (
    ABTest,
    Enrollment,
    EnrollmentStatus,
    Sequence,
    SequenceStatus,
    SequenceStep,
    StepRun,
    StepRunStatus,
)
from app.services import (
    approval_service,
    consent_service,
    email_service,
    lead_service,
    outbox,
    sequence_service,
    template_service,
)


# --- Enrollment -------------------------------------------------------------
async def enroll(db: AsyncSession, sequence: Sequence, lead_id: uuid.UUID) -> Enrollment | None:
    """Enroll a lead. Returns the enrollment, or None if the sequence is not
    active, has no steps, or the lead is already enrolled."""
    if sequence.status != SequenceStatus.active:
        return None
    steps = await sequence_service.list_steps(db, sequence.id)
    if not steps:
        return None

    existing = await db.execute(
        select(Enrollment).where(
            Enrollment.sequence_id == sequence.id, Enrollment.lead_id == lead_id
        )
    )
    if existing.scalar_one_or_none() is not None:
        return None

    now = utcnow()
    enrollment = Enrollment(
        sequence_id=sequence.id, brand_id=sequence.brand_id, lead_id=lead_id,
        status=EnrollmentStatus.active, current_step_index=0, enrolled_at=now,
        next_run_at=now + timedelta(minutes=steps[0].delay_minutes),
    )
    db.add(enrollment)
    await db.flush()
    await db.refresh(enrollment)
    return enrollment


async def enroll_lead_if_configured(db: AsyncSession, form, lead_id: uuid.UUID) -> None:
    """Hook used by the lead-capture confirm flow: enroll into the form's
    configured sequence when the lead becomes mailable."""
    if not form.enroll_sequence_id:
        return
    sequence = await db.get(Sequence, form.enroll_sequence_id)
    if sequence and sequence.deleted_at is None:
        await enroll(db, sequence, lead_id)


# --- Rendering + A/B --------------------------------------------------------
def _pick_variant(variants: list[dict], enrollment_id: uuid.UUID) -> dict:
    """Deterministic weighted variant pick (stable per enrollment)."""
    total = sum(max(1, v.get("weight", 1)) for v in variants)
    bucket = int(hashlib.sha256(enrollment_id.bytes).hexdigest(), 16) % total
    cumulative = 0
    for v in variants:
        cumulative += max(1, v.get("weight", 1))
        if bucket < cumulative:
            return v
    return variants[-1]


async def _render_step(
    db: AsyncSession, step: SequenceStep, enrollment: Enrollment, lead: Lead, brand: Brand
) -> tuple[str, str, str | None, str | None, str]:
    unsub = consent_service.make_unsubscribe_url(lead.id)
    ctx = {
        "first_name": lead.first_name or "there", "last_name": lead.last_name or "",
        "email": lead.email, "brand_name": brand.name, "unsubscribe_url": unsub,
    }
    subject = step.subject or ""
    html = step.html_body or ""
    text = step.text_body

    if step.template_id:
        from app.models.email import EmailTemplate
        tpl = await db.get(EmailTemplate, step.template_id)
        if tpl:
            subject = subject or tpl.subject
            html = html or tpl.html_body
            text = text or tpl.text_body

    variant_label = None
    ab = (await db.execute(
        select(ABTest).where(ABTest.sequence_step_id == step.id)
    )).scalar_one_or_none()
    if ab and ab.variants:
        variant = _pick_variant(ab.variants, enrollment.id)
        subject = variant["subject"]
        variant_label = variant["label"]

    subject_r = template_service.render_string(subject, ctx)
    html_r = template_service.render_string(html, ctx)
    if "unsubscribe" not in html_r.lower():
        html_r += (f'<p style="font-size:12px;color:#888;margin-top:24px">'
                   f'<a href="{unsub}">Unsubscribe</a></p>')
    text_r = template_service.render_string(text, ctx) if text else None
    return subject_r, html_r, text_r, variant_label, unsub


# --- Sending ----------------------------------------------------------------
async def _send_step(
    db: AsyncSession, enrollment: Enrollment, step: SequenceStep, sequence: Sequence, lead: Lead
) -> bool:
    brand = await db.get(Brand, sequence.brand_id)
    subject, html, text, variant_label, unsub = await _render_step(
        db, step, enrollment, lead, brand
    )
    from_email, from_name = await outbox.resolve_sender(db, sequence.brand_id)
    message = EmailMessage(
        brand_id=sequence.brand_id, lead_id=lead.id, to_email=lead.email,
        from_email=from_email, from_name=from_name, subject=subject, html_body=html,
        text_body=text, category=EmailCategory.sequence, status=EmailStatus.draft,
        variant_label=variant_label,
    )
    db.add(message)
    await db.flush()
    await email_service.send_message(db, message, unsubscribe_url=unsub)

    db.add(StepRun(
        enrollment_id=enrollment.id, sequence_step_id=step.id,
        status=StepRunStatus.sent if message.status == EmailStatus.sent else StepRunStatus.failed,
        sent_at=utcnow(), email_message_id=message.id, variant_label=variant_label,
    ))
    await db.flush()
    return message.status == EmailStatus.sent


async def _request_step_approval(
    db: AsyncSession, enrollment: Enrollment, step: SequenceStep, sequence: Sequence
) -> None:
    step_run = StepRun(
        enrollment_id=enrollment.id, sequence_step_id=step.id,
        status=StepRunStatus.pending_approval, scheduled_at=utcnow(),
    )
    db.add(step_run)
    await db.flush()
    await approval_service.create_approval(
        db, action_type=ApprovalAction.sequence_step_send, brand_id=sequence.brand_id,
        title=f"Send step “{step.name or step.order_index}” of “{sequence.name}”",
        entity_type="step_run", entity_id=step_run.id,
        summary=f"Subject: {step.subject or '(from template)'}",
        payload={"enrollment_id": str(enrollment.id), "step_id": str(step.id)},
    )


def _advance(enrollment: Enrollment, steps: list[SequenceStep], now) -> bool:
    """Move to the next step; return True if the sequence is now complete."""
    enrollment.current_step_index += 1
    if enrollment.current_step_index >= len(steps):
        enrollment.status = EnrollmentStatus.completed
        enrollment.completed_at = now
        enrollment.next_run_at = None
        return True
    nxt = steps[enrollment.current_step_index]
    enrollment.next_run_at = now + timedelta(minutes=nxt.delay_minutes)
    return False


async def _passes_condition(db: AsyncSession, step: SequenceStep, lead: Lead) -> bool:
    required_tag = step.condition.get("require_tag") if step.condition else None
    if required_tag:
        tags = await lead_service.list_lead_tags(db, lead.id)
        return any(t.name == required_tag for t in tags)
    return True


# --- Tick -------------------------------------------------------------------
async def tick_due(db: AsyncSession, *, now=None, limit: int = 200) -> dict:
    now = now or utcnow()
    stats = {"processed": 0, "sent": 0, "completed": 0, "awaiting_approval": 0, "stopped": 0}

    result = await db.execute(
        select(Enrollment).where(
            Enrollment.status == EnrollmentStatus.active,
            Enrollment.next_run_at.is_not(None),
            Enrollment.next_run_at <= now,
        ).limit(limit)
    )
    for enrollment in result.scalars().all():
        stats["processed"] += 1
        sequence = await db.get(Sequence, enrollment.sequence_id)
        if sequence is None or sequence.status != SequenceStatus.active:
            continue  # paused/archived sequence — leave enrollment for later
        steps = await sequence_service.list_steps(db, sequence.id)

        lead = await db.get(Lead, enrollment.lead_id) if enrollment.lead_id else None
        if lead is None:
            enrollment.status = EnrollmentStatus.stopped
            enrollment.stop_reason = "lead missing"
            stats["stopped"] += 1
            continue
        if lead.consent_status == ConsentStatus.unsubscribed:
            enrollment.status = EnrollmentStatus.unsubscribed
            enrollment.stop_reason = "unsubscribed"
            stats["stopped"] += 1
            continue
        if enrollment.current_step_index >= len(steps):
            enrollment.status = EnrollmentStatus.completed
            enrollment.completed_at = now
            stats["completed"] += 1
            continue

        step = steps[enrollment.current_step_index]
        if not await _passes_condition(db, step, lead):
            if _advance(enrollment, steps, now):
                stats["completed"] += 1
            continue

        if step.require_approval or sequence.require_approval:
            await _request_step_approval(db, enrollment, step, sequence)
            enrollment.next_run_at = None  # wait for human decision
            stats["awaiting_approval"] += 1
            continue

        if await _send_step(db, enrollment, step, sequence, lead):
            stats["sent"] += 1
        if _advance(enrollment, steps, now):
            stats["completed"] += 1

    await db.flush()
    return stats


# --- Approval execution -----------------------------------------------------
async def execute_step_run(db: AsyncSession, step_run_id: uuid.UUID) -> bool:
    """Send a previously approval-gated step run, then advance its enrollment."""
    step_run = await db.get(StepRun, step_run_id)
    if step_run is None or step_run.status != StepRunStatus.pending_approval:
        return False
    enrollment = await db.get(Enrollment, step_run.enrollment_id)
    step = await db.get(SequenceStep, step_run.sequence_step_id)
    sequence = await db.get(Sequence, enrollment.sequence_id) if enrollment else None
    lead = await db.get(Lead, enrollment.lead_id) if enrollment and enrollment.lead_id else None
    if not (enrollment and step and sequence and lead):
        return False

    brand = await db.get(Brand, sequence.brand_id)
    subject, html, text, variant_label, unsub = await _render_step(
        db, step, enrollment, lead, brand
    )
    from_email, from_name = await outbox.resolve_sender(db, sequence.brand_id)
    message = EmailMessage(
        brand_id=sequence.brand_id, lead_id=lead.id, to_email=lead.email,
        from_email=from_email, from_name=from_name, subject=subject, html_body=html,
        text_body=text, category=EmailCategory.sequence, status=EmailStatus.draft,
        step_run_id=step_run.id, variant_label=variant_label,
    )
    db.add(message)
    await db.flush()
    await email_service.send_message(db, message, unsubscribe_url=unsub)

    step_run.status = (StepRunStatus.sent if message.status == EmailStatus.sent
                       else StepRunStatus.failed)
    step_run.sent_at = utcnow()
    step_run.email_message_id = message.id
    db.add(step_run)

    steps = await sequence_service.list_steps(db, sequence.id)
    _advance(enrollment, steps, utcnow())
    db.add(enrollment)
    await db.flush()
    return message.status == EmailStatus.sent


# --- Goals + pause/resume ---------------------------------------------------
async def record_goal(db: AsyncSession, *, lead_id: uuid.UUID, event_name: str) -> int:
    result = await db.execute(
        select(Enrollment).join(Sequence, Sequence.id == Enrollment.sequence_id).where(
            Enrollment.lead_id == lead_id,
            Enrollment.status == EnrollmentStatus.active,
            Sequence.stop_on_goal.is_(True),
            Sequence.goal_event == event_name,
        )
    )
    now = utcnow()
    count = 0
    for enrollment in result.scalars().all():
        enrollment.status = EnrollmentStatus.goal_met
        enrollment.completed_at = now
        enrollment.next_run_at = None
        db.add(enrollment)
        count += 1
    await db.flush()
    return count


async def set_enrollment_state(
    db: AsyncSession, enrollment: Enrollment, *, paused: bool
) -> Enrollment:
    if paused:
        enrollment.status = EnrollmentStatus.paused
        enrollment.paused_at = utcnow()
    else:
        enrollment.status = EnrollmentStatus.active
        if enrollment.next_run_at is None:
            enrollment.next_run_at = utcnow()
    db.add(enrollment)
    await db.flush()
    await db.refresh(enrollment)
    return enrollment
