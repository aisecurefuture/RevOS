"""Third-party industry benchmarks — CRUD + lookup (BM1) + paste-and-parse
extraction assist (BM3).

Admin-curated figures read off published reports, used as the fallback when
RevOS's own cohort benchmarks (insights_service, public_profile_service) are
too thin. Writes are platform-admin only (enforced by the router); this
module does the CRUD, the "give me the current figure" lookup, and the
AI-assisted extraction that turns pasted report text into draft rows for an
admin to review before anything saves.
"""

from __future__ import annotations

import json
import logging
import uuid

from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from app.core.exceptions import RevOSError
from app.models.benchmark import IndustryBenchmark
from app.services.industry_taxonomy import CATEGORIES

logger = logging.getLogger("revos.matching.benchmarks")

_VALID_PLATFORMS = {"all", "facebook", "instagram", "linkedin", "threads", "tiktok", "twitter", "youtube"}

_EXTRACT_SYSTEM = (
    "You extract social-media engagement-rate benchmark figures from raw text "
    "copied from a published industry report (e.g. Rival IQ/Quid, Socialinsider). "
    "Return ONLY a JSON array (no prose, no markdown fences) of objects shaped "
    "exactly like: "
    '{"industry_category": "<slug>", "industry_label": "<verbatim industry name '
    'from the report>", "platform": "<platform>", "metric": "engagement_rate", '
    '"value": <decimal fraction>}. '
    "industry_label MUST be the industry name exactly as the report states it "
    "(e.g. \"Veterinary Services\", \"Nonprofit\") — never omit or paraphrase it, "
    "even when it doesn't map cleanly onto a category below. "
    f"industry_category MUST be one of exactly: {', '.join(CATEGORIES)} — map "
    "industry_label to the closest one of these for cohort-comparison purposes; "
    "use \"other\" only when nothing fits, and still include the real "
    "industry_label in that case rather than dropping the row. "
    f"platform MUST be one of exactly: {', '.join(sorted(_VALID_PLATFORMS))} — use "
    "\"all\" if the figure isn't platform-specific. "
    "value is a decimal fraction, e.g. a reported \"2.1%\" becomes 0.021 — never "
    "a percentage-scale number like 2.1. "
    "If you cannot confidently extract any rows, return an empty array []."
)


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


# --- BM3: paste-and-parse extraction assist ---------------------------------
def extract_from_text(text: str) -> dict:
    """Turn pasted report text into DRAFT rows for an admin to review — never
    saves anything itself. Returns {"rows": [...], "unparsed_note": str|None}.
    Every row is validated against the same allow-lists the manual-entry
    endpoint enforces; a malformed or invalid row is dropped and named in
    unparsed_note rather than silently guessed at or allowed through."""
    from app.services import ai_service

    raw = ai_service.analyze(system=_EXTRACT_SYSTEM, context=text, max_tokens=2000)
    if raw is None:
        raise RevOSError(
            "AI extraction isn't available right now (no provider configured, or the "
            "call failed) — add rows manually instead.",
            code="ai_unavailable", status_code=503,
        )

    try:
        parsed = json.loads(raw)
        if not isinstance(parsed, list):
            raise ValueError("not a list")
    except (json.JSONDecodeError, ValueError):
        logger.warning("Benchmark extraction returned non-JSON output: %r", raw[:500])
        return {"rows": [], "unparsed_note": "The AI's response wasn't valid JSON — try again, "
                "or add the rows manually."}

    rows: list[dict] = []
    dropped = 0
    for item in parsed:
        if not isinstance(item, dict):
            dropped += 1
            continue
        category = item.get("industry_category")
        label = item.get("industry_label")
        label = label.strip()[:120] if isinstance(label, str) and label.strip() else None
        platform = item.get("platform", "all")
        metric = item.get("metric", "engagement_rate")
        value = item.get("value")
        if (category not in CATEGORIES or platform not in _VALID_PLATFORMS
                or not isinstance(value, (int, float)) or not (0 <= value <= 1)):
            dropped += 1
            continue
        rows.append({
            "industry_category": category, "industry_label": label, "platform": platform,
            "metric": metric, "value": float(value),
        })

    note = f"{dropped} row(s) couldn't be confidently extracted and were skipped." if dropped else None
    return {"rows": rows, "unparsed_note": note}


async def bulk_create(db: AsyncSession, *, rows: list[dict], source: str,
                      source_url: str | None, period_label: str,
                      updated_by_user_id: uuid.UUID) -> dict:
    """Save admin-reviewed rows from the extraction draft. One row's
    duplicate doesn't fail the whole batch — it's just skipped and reported,
    same as if the admin had added it manually and hit duplicate_benchmark."""
    created = 0
    skipped: list[dict] = []
    for row in rows:
        try:
            await create(db, {**row, "source": source, "source_url": source_url,
                             "period_label": period_label}, updated_by_user_id=updated_by_user_id)
            created += 1
        except RevOSError as exc:
            if exc.code != "duplicate_benchmark":
                raise
            skipped.append(row)
    return {"created": created, "skipped": skipped}
