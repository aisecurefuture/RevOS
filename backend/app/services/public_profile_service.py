"""Public creator page + QR sharing (Phase 6).

A creator's marketing page for the open internet — no login, meant to be
linked from a QR code on business cards/social bios. Deliberately a SEPARATE
opt-in from ``discoverable`` (internal marketplace visibility to logged-in
brands): this is public to anyone, so the creator also picks exactly which
fields show, enforced server-side against ``PUBLIC_CREATOR_FIELDS`` — a
tampered request can never add a field outside that allow-list.
"""

from __future__ import annotations

import re
import uuid
from datetime import datetime

from sqlalchemy import func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from app.core.exceptions import RevOSError
from app.models.base import utcnow
from app.models.matching import Creator, CreatorStatus
from app.models.reputation import Certification, CertificationStatus, CertificationSubjectType
from app.schemas.matching import PUBLIC_CREATOR_FIELDS
from app.services import reputation_service
from app.services.industry_taxonomy import INDUSTRY_CATEGORY, rollup

_TIER_BANDS: tuple[tuple[float, str], ...] = (
    (80.0, "Top-Rated"), (60.0, "Trusted"), (40.0, "Growing"), (0.0, "New"),
)
_MAX_COHORT_FOR_PERCENTILE = 40   # bound the per-peer reputation computation cost


def _tier_for(overall: float) -> str:
    for floor, label in _TIER_BANDS:
        if overall >= floor:
            return label
    return "New"


def _slugify(text: str) -> str:
    base = re.sub(r"[^a-z0-9]+", "-", (text or "").lower()).strip("-")
    return (base or "creator")[:100]


async def _unique_slug(db: AsyncSession, base: str, *, exclude_creator_id: uuid.UUID) -> str:
    slug = _slugify(base)
    candidate = slug
    suffix = 1
    while True:
        existing = (await db.execute(select(Creator.id).where(
            Creator.public_slug == candidate, Creator.id != exclude_creator_id))).scalar_one_or_none()
        if existing is None:
            return candidate
        suffix += 1
        candidate = f"{slug}-{suffix}"


async def update_public_page(db: AsyncSession, creator: Creator, *,
                             enabled: bool, slug: str | None, fields: list[str]) -> Creator:
    bad = [f for f in fields if f not in PUBLIC_CREATOR_FIELDS]
    if bad:
        raise RevOSError(f"Unsupported public field(s): {', '.join(bad)}.",
                         code="invalid_field", status_code=400)

    creator.public_page_enabled = enabled
    creator.public_fields = fields
    if enabled:
        desired = slug.strip() if slug and slug.strip() else (creator.public_slug or creator.display_name)
        if slug and slug.strip():
            # An explicit slug request must not silently collide with someone else's.
            taken = (await db.execute(select(Creator.id).where(
                Creator.public_slug == _slugify(desired), Creator.id != creator.id))).scalar_one_or_none()
            if taken is not None:
                raise RevOSError("That link is already taken — try another.",
                                 code="slug_taken", status_code=409)
            creator.public_slug = _slugify(desired)
        elif not creator.public_slug:
            creator.public_slug = await _unique_slug(db, desired, exclude_creator_id=creator.id)
    db.add(creator)
    await db.flush()
    await db.refresh(creator)
    return creator


async def _reputation_percentile(db: AsyncSession, creator: Creator, overall: float) -> int | None:
    category = rollup(creator.industry)
    if not category or not creator.size_tier:
        return None
    slugs = [s for s, c in INDUSTRY_CATEGORY.items() if c == category]
    peers = (await db.execute(select(Creator).where(
        Creator.industry.in_(slugs), Creator.size_tier == creator.size_tier,
        Creator.status == CreatorStatus.active, Creator.deleted_at.is_(None),
        Creator.id != creator.id,
    ).limit(_MAX_COHORT_FOR_PERCENTILE))).scalars().all()
    if len(peers) < 2:
        return None
    now = utcnow()
    below = 0
    for peer in peers:
        peer_score = await reputation_service.reputation_for(
            db, subject_type="creator", subject_id=peer.id, account_id=peer.account_id, now=now)
        if peer_score.overall < overall:
            below += 1
    return round(below / len(peers) * 100)


async def get_public_page(db: AsyncSession, slug: str) -> dict | None:
    creator = (await db.execute(select(Creator).where(
        Creator.public_slug == slug, Creator.public_page_enabled == True,  # noqa: E712
        Creator.deleted_at.is_(None), Creator.status == CreatorStatus.active,
    ))).scalar_one_or_none()
    if creator is None:
        return None

    creator.public_view_count += 1
    creator.public_last_viewed_at = utcnow()
    db.add(creator)
    await db.flush()

    fields = set(creator.public_fields or [])
    out: dict = {
        "display_name": creator.display_name, "handle": creator.handle,
        "slug": creator.public_slug, "view_count": creator.public_view_count,
        "topics": [], "certifications": [],
    }
    if "bio" in fields:
        out["bio"] = creator.bio
    if "industry" in fields:
        out["industry"] = creator.industry
    if "location" in fields:
        out["location"] = creator.location
    if "size_tier" in fields:
        out["size_tier"] = creator.size_tier
    if "follower_count" in fields:
        out["follower_count"] = creator.follower_count
    if "engagement_rate" in fields:
        out["engagement_rate"] = creator.engagement_rate
        # A comparative claim needs a citation for credibility — the same
        # cohort-first/industry-report-fallback benchmark used on the
        # private dashboard (insights_service.engagement_benchmark), just
        # surfaced publicly since the creator already opted into showing the
        # raw number.
        from app.services import insights_service
        out["engagement_benchmark"] = await insights_service.engagement_benchmark(db, creator)
    if "topics" in fields:
        out["topics"] = creator.topics or []

    if "reputation" in fields:
        score = await reputation_service.reputation_for(
            db, subject_type="creator", subject_id=creator.id,
            account_id=creator.account_id, now=utcnow())
        percentile = await _reputation_percentile(db, creator, score.overall)
        out["reputation"] = {
            "overall": round(score.overall, 1), "tier": _tier_for(score.overall),
            "percentile": percentile,
        }

    if "certifications" in fields:
        certs = (await db.execute(select(Certification).where(
            Certification.subject_type == CertificationSubjectType.creator,
            Certification.subject_id == creator.id,
            Certification.status == CertificationStatus.active, Certification.deleted_at.is_(None),
        ))).scalars().all()
        out["certifications"] = [
            {"name": c.name, "issuer": c.issuer, "verified": c.verified} for c in certs
        ]

    return out
