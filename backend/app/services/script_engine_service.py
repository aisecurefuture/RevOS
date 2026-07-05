"""Viral video script engine (Phase 3 M4).

Generates the spoken script for a talking-head avatar video, grounded in the
brand book and sized to a target duration, then runs it through the brand-book
accuracy gate. This is the bridge between the Brand Book (M1) and avatar
generation (M3): a fast, cheap, reviewable text step before the slow render.

Duration control: video length is driven by audio length, which is driven by
word count — so we size the script to ``target_seconds`` at a natural short-form
speaking rate (~150 wpm) and instruct the model to hit that budget.
"""

from __future__ import annotations

import asyncio
import re
import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import NotFoundError, RevOSError
from app.models.base import utcnow
from app.models.brand import Brand
from app.models.persona_identity import PersonaIdentity
from app.models.user import AdminUser
from app.models.video_script import VideoScript
from app.services import ai_service, brand_book_service

# Natural short-form speaking rate. 150 wpm = 2.5 words/sec.
_WORDS_PER_SECOND = 2.5


def word_target(target_seconds: int) -> int:
    return max(5, round(target_seconds * _WORDS_PER_SECOND))


def _first_sentence(text: str) -> str:
    parts = re.split(r"(?<=[.!?])\s+", text.strip(), maxsplit=1)
    return (parts[0] if parts else text).strip()[:500]


async def _brand_in_account(db: AsyncSession, brand_id: uuid.UUID, account_id: uuid.UUID) -> Brand:
    brand = await db.get(Brand, brand_id)
    if brand is None or brand.account_id != account_id or brand.deleted_at is not None:
        raise NotFoundError("Brand not found.")
    return brand


# ---------------------------------------------------------------------------
# Generation
# ---------------------------------------------------------------------------

async def generate_script(
    db: AsyncSession, account_id: uuid.UUID, user: AdminUser, *,
    brand_id: uuid.UUID, target_seconds: int,
    persona_identity_id: uuid.UUID | None = None, angle: str | None = None,
) -> VideoScript:
    await _brand_in_account(db, brand_id, account_id)

    persona: PersonaIdentity | None = None
    if persona_identity_id is not None:
        result = await db.execute(
            select(PersonaIdentity).where(
                PersonaIdentity.id == persona_identity_id,
                PersonaIdentity.account_id == account_id,
                PersonaIdentity.deleted_at.is_(None),
            )
        )
        persona = result.scalar_one_or_none()
        if persona is None:
            raise NotFoundError("Persona not found.")

    grounding = await brand_book_service.assemble_grounding_context(db, brand_id)
    words = word_target(target_seconds)

    system = (
        "You are an elite short-form video scriptwriter. Write ONE spoken script for a "
        f"{target_seconds}-second talking-head video — about {words} words, spoken aloud in "
        "first person by the person described below. "
        "Structure: open with a scroll-stopping HOOK in the very first sentence; deliver ONE "
        "clear, valuable point; end with a single strong call to action. "
        "Write natural spoken language ONLY — the exact words to be said. No hashtags, no "
        "emoji, no stage directions, no scene descriptions, no speaker labels. "
        "State facts ONLY from the Approved claims in the context; never invent statistics, "
        "metrics, or facts."
    )
    context = grounding.prompt_context
    if persona is not None:
        speaker = [f"\n## Speaker\nSpoken in first person by {persona.name}."]
        if persona.voice_notes:
            speaker.append(f"Voice: {persona.voice_notes}")
        if persona.appearance_notes:
            speaker.append(f"Appearance: {persona.appearance_notes}")
        context += "\n".join(speaker)
    if angle:
        context += f"\n\n## This video's angle\n{angle}"

    text = await asyncio.to_thread(
        ai_service.generate,
        system=system, context=context,
        max_tokens=min(1500, words * 4 + 120), use_case="social",
    )
    if not text:
        raise RevOSError(
            "No AI provider is configured, so scripts can't be generated. Set AI_PROVIDER "
            "(e.g. a local Ollama model) on the server.",
            code="ai_unavailable", status_code=503,
        )
    text = text.strip()

    check = await brand_book_service.verify_content(db, brand_id, text)
    script = VideoScript(
        account_id=account_id, brand_id=brand_id, persona_identity_id=persona_identity_id,
        target_seconds=target_seconds, angle=angle,
        script=text, hook=_first_sentence(text), word_count=len(text.split()),
        passed_gate=check.passed, gate=check.to_dict(),
        created_by=user.id,
    )
    db.add(script)
    await db.flush()
    await db.refresh(script)
    return script


# ---------------------------------------------------------------------------
# CRUD
# ---------------------------------------------------------------------------

async def list_scripts(
    db: AsyncSession, account_id: uuid.UUID,
    brand_id: uuid.UUID | None = None, persona_identity_id: uuid.UUID | None = None,
) -> list[VideoScript]:
    filters = [VideoScript.account_id == account_id, VideoScript.deleted_at.is_(None)]
    if brand_id is not None:
        filters.append(VideoScript.brand_id == brand_id)
    if persona_identity_id is not None:
        filters.append(VideoScript.persona_identity_id == persona_identity_id)
    result = await db.execute(
        select(VideoScript).where(*filters).order_by(VideoScript.created_at.desc())
    )
    return list(result.scalars().all())


async def get_script(db: AsyncSession, script_id: uuid.UUID, account_id: uuid.UUID) -> VideoScript:
    result = await db.execute(
        select(VideoScript).where(
            VideoScript.id == script_id,
            VideoScript.account_id == account_id,
            VideoScript.deleted_at.is_(None),
        )
    )
    script = result.scalar_one_or_none()
    if script is None:
        raise NotFoundError("Script not found.")
    return script


async def update_script(
    db: AsyncSession, script_id: uuid.UUID, account_id: uuid.UUID, new_text: str,
) -> VideoScript:
    """Edit a script's text and re-run the accuracy gate on the edited version."""
    script = await get_script(db, script_id, account_id)
    new_text = new_text.strip()
    if not new_text:
        raise RevOSError("Script cannot be empty.", code="empty_script", status_code=400)
    check = await brand_book_service.verify_content(db, script.brand_id, new_text)
    script.script = new_text
    script.hook = _first_sentence(new_text)
    script.word_count = len(new_text.split())
    script.passed_gate = check.passed
    script.gate = check.to_dict()
    db.add(script)
    await db.flush()
    await db.refresh(script)
    return script


async def delete_script(db: AsyncSession, script_id: uuid.UUID, account_id: uuid.UUID) -> None:
    script = await get_script(db, script_id, account_id)
    script.deleted_at = utcnow()
    db.add(script)
    await db.flush()
