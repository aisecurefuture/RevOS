"""Content engine: items, the approval state machine, libraries, calendar, ideas."""

from __future__ import annotations

import uuid

from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from app.core.exceptions import RevOSError
from app.core.sanitize import strip_all
from app.core.text import clean_text
from app.models.base import utcnow
from app.models.content import (
    CTA,
    ContentCalendar,
    ContentItem,
    ContentState,
    Hashtag,
    Hook,
    Pillar,
)
from app.services.crud import get_active, list_active

# Allowed content state transitions (Draft → Needs review → Approved →
# Scheduled → Published → Archived, with sensible reverts).
TRANSITIONS: dict[ContentState, set[ContentState]] = {
    ContentState.draft: {ContentState.needs_review, ContentState.approved,
                         ContentState.scheduled, ContentState.archived},
    ContentState.needs_review: {ContentState.approved, ContentState.draft,
                                ContentState.archived},
    ContentState.approved: {ContentState.scheduled, ContentState.published,
                            ContentState.draft, ContentState.archived},
    ContentState.scheduled: {ContentState.published, ContentState.approved,
                             ContentState.archived},
    ContentState.published: {ContentState.archived},
    ContentState.archived: {ContentState.draft},
}


def can_transition(current: ContentState, target: ContentState) -> bool:
    return target in TRANSITIONS.get(current, set())


async def create_content(db: AsyncSession, data: dict) -> ContentItem:
    data["title"] = clean_text(data["title"]) or data["title"]
    item = ContentItem(**data)
    db.add(item)
    await db.flush()
    await db.refresh(item)
    return item


async def update_content(db: AsyncSession, item: ContentItem, data: dict) -> ContentItem:
    if "title" in data and data["title"] is not None:
        data["title"] = clean_text(data["title"])
    for key, value in data.items():
        setattr(item, key, value)
    db.add(item)
    await db.flush()
    await db.refresh(item)
    return item


async def transition(
    db: AsyncSession, item: ContentItem, target: ContentState, *, scheduled_at=None
) -> ContentItem:
    if not can_transition(item.state, target):
        raise RevOSError(f"Cannot move content from {item.state} to {target}.")
    item.state = target
    if target == ContentState.scheduled and scheduled_at is not None:
        item.scheduled_at = scheduled_at
    if target == ContentState.published:
        item.published_at = utcnow()
    db.add(item)
    await db.flush()
    await db.refresh(item)
    return item


async def list_content(
    db: AsyncSession, *, brand_id: uuid.UUID | None = None, channel=None, state=None,
    calendar_id: uuid.UUID | None = None, limit: int = 50, offset: int = 0,
) -> list[ContentItem]:
    filters: list = []
    if brand_id:
        filters.append(ContentItem.brand_id == brand_id)
    if channel:
        filters.append(ContentItem.channel == channel)
    if state:
        filters.append(ContentItem.state == state)
    if calendar_id:
        filters.append(ContentItem.calendar_id == calendar_id)
    return await list_active(db, ContentItem, filters=filters, limit=limit, offset=offset)


# --- Libraries (pillars / hooks / CTAs / hashtags) --------------------------
async def create_library_item(db: AsyncSession, model, data: dict):
    obj = model(**data)
    db.add(obj)
    await db.flush()
    await db.refresh(obj)
    return obj


async def list_library(db: AsyncSession, model, brand_id: uuid.UUID | None):
    # Brand-scoped items plus global (brand_id NULL) ones.
    stmt = select(model).where(model.deleted_at.is_(None))
    if brand_id:
        stmt = stmt.where((model.brand_id == brand_id) | (model.brand_id.is_(None)))
    result = await db.execute(stmt.limit(200))
    return list(result.scalars().all())


# --- Calendar ---------------------------------------------------------------
async def create_calendar(db: AsyncSession, data: dict) -> ContentCalendar:
    cal = ContentCalendar(**data)
    db.add(cal)
    await db.flush()
    await db.refresh(cal)
    return cal


async def list_calendars(db: AsyncSession, brand_id: uuid.UUID | None) -> list[ContentCalendar]:
    filters = [ContentCalendar.brand_id == brand_id] if brand_id else []
    return await list_active(db, ContentCalendar, filters=filters)


# --- Idea generation (template-based; AI provider plugs in at Module 14) -----
_TEMPLATES = [
    "{pillar}: a {channel} post sharing one hard-won lesson about {topic}.",
    "{pillar}: a contrarian take on {topic} for {channel}.",
    "{pillar}: a short how-to / checklist about {topic}.",
    "{pillar}: a customer story or proof point related to {topic}.",
    "{pillar}: a myth-vs-reality breakdown of {topic}.",
    "{pillar}: a behind-the-scenes look connected to {topic}.",
]


async def generate_ideas(
    db: AsyncSession, *, brand, channel: str, count: int, topic: str | None
) -> tuple[list[str], str]:
    """Return (ideas, source). Uses the AI provider when configured; otherwise a
    deterministic, pillar-driven template generator."""
    from app.services import ai_service

    subject = strip_all(topic) if topic else brand.name
    if ai_service.ai_available():
        out = ai_service.generate(
            system=f"List {count} concrete {channel.replace('_', ' ')} content ideas "
                   "as a plain bullet list, one per line.",
            context=f"Brand: {brand.name}\nTopic: {subject}", max_tokens=400)
        if out:
            ideas = [ln.lstrip("-*0123456789. ").strip()
                     for ln in out.splitlines() if ln.strip()]
            if ideas:
                return ideas[:count], "ai"

    pillars = await list_library(db, Pillar, brand.id)
    pillar_names = [p.name for p in pillars] or ["Thought leadership", "Education", "Proof"]
    ideas = []
    i = 0
    while len(ideas) < count:
        template = _TEMPLATES[i % len(_TEMPLATES)]
        pillar = pillar_names[i % len(pillar_names)]
        ideas.append(template.format(pillar=pillar, channel=channel.replace("_", " "),
                                     topic=subject))
        i += 1
    return ideas, "template"


async def repurpose(
    db: AsyncSession, source: ContentItem, channels: list[str]
) -> list[ContentItem]:
    """Create draft items for other channels from a source piece (deterministic;
    AI can rewrite each in Module 14)."""
    created = []
    excerpt = (source.body or "")[:280]
    for channel in channels:
        item = ContentItem(
            brand_id=source.brand_id, channel=channel,
            title=f"{source.title} — {channel}", body=excerpt,
            hashtags=source.hashtags, source_content_id=source.id,
            state=ContentState.draft,
        )
        db.add(item)
        created.append(item)
    await db.flush()
    return created


async def get_content_or_404(db: AsyncSession, item_id: uuid.UUID) -> ContentItem:
    return await get_active(db, ContentItem, item_id)


# Re-exported for routers
LIBRARY_MODELS = {"pillars": Pillar, "hooks": Hook, "ctas": CTA, "hashtags": Hashtag}
