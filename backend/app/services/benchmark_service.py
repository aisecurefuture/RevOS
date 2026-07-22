"""Third-party industry benchmarks — CRUD + lookup (BM1).

Admin-curated figures read off published reports, used as the fallback when
RevOS's own cohort benchmarks (insights_service, public_profile_service) are
too thin. Writes are platform-admin only (enforced by the router); this
module itself just does the CRUD + "give me the current figure" lookup.
"""

from __future__ import annotations

import uuid

from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from app.core.exceptions import RevOSError
from app.models.benchmark import IndustryBenchmark


async def create(db: AsyncSession, data: dict, *, updated_by_user_id: uuid.UUID) -> IndustryBenchmark:
    existing = (await db.execute(select(IndustryBenchmark).where(
        IndustryBenchmark.industry_category == data["industry_category"],
        IndustryBenchmark.platform == data.get("platform", "all"),
        IndustryBenchmark.metric == data.get("metric", "engagement_rate"),
        IndustryBenchmark.period_label == data["period_label"],
        IndustryBenchmark.deleted_at.is_(None),
    ))).scalar_one_or_none()
    if existing is not None:
        raise RevOSError(
            "A benchmark for this category/platform/metric/period already exists — "
            "delete it first if you want to replace it.",
            code="duplicate_benchmark", status_code=409,
        )
    row = IndustryBenchmark(**data, updated_by_user_id=updated_by_user_id)
    db.add(row)
    await db.flush()
    await db.refresh(row)
    return row


async def list_all(db: AsyncSession, *, industry_category: str | None = None) -> list[IndustryBenchmark]:
    stmt = select(IndustryBenchmark).where(IndustryBenchmark.deleted_at.is_(None))
    if industry_category:
        stmt = stmt.where(IndustryBenchmark.industry_category == industry_category)
    stmt = stmt.order_by(IndustryBenchmark.industry_category, IndustryBenchmark.platform,
                         IndustryBenchmark.updated_at.desc())
    return list((await db.execute(stmt)).scalars().all())


async def delete(db: AsyncSession, row: IndustryBenchmark) -> None:
    from app.models.base import utcnow
    row.deleted_at = utcnow()
    db.add(row)
    await db.flush()


async def get_current(db: AsyncSession, *, industry_category: str, metric: str = "engagement_rate",
                      platform: str | None = None) -> IndustryBenchmark | None:
    """The most recently updated figure for this category+metric. Tries the
    specific platform first, then falls back to the cross-platform ("all")
    figure — so a caller doesn't need a benchmark for every single platform
    to get *something* useful."""
    for candidate_platform in ([platform] if platform else []) + ["all"]:
        stmt = select(IndustryBenchmark).where(
            IndustryBenchmark.industry_category == industry_category,
            IndustryBenchmark.platform == candidate_platform,
            IndustryBenchmark.metric == metric,
            IndustryBenchmark.deleted_at.is_(None),
        ).order_by(IndustryBenchmark.updated_at.desc()).limit(1)
        row = (await db.execute(stmt)).scalar_one_or_none()
        if row is not None:
            return row
    return None
