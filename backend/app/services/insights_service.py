"""Insight dashboards — benchmarked performance + recommendations (Phase 4, IK1).

"Beyond A/B testing" because the comparison set is the *market*, not just your
own past: a creator or brand sees its own metrics, how it ranks against peers in
the same industry-rollup + size cohort, and a prioritized list of what's working
and what to fix.

Own-subject metrics (reputation, review average, request rates) are cheap to
compute for one subject. Cohort benchmarks aggregate cheap columnar metrics
(engagement, reach) in SQL over the whole marketplace population — privacy-safe
because only anonymous aggregates (averages, percentiles, counts) leave the
cohort, never individuals. Recommendations blend cohort comparison with absolute
quality thresholds.
"""

from __future__ import annotations

import uuid

from sqlalchemy import func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from app.models.collaboration import (
    AssetState,
    Collaboration,
    CollaborationAsset,
    CollaborationDeliverable,
    CollaborationState,
    DeliverableStatus,
)
from app.models.matching import (
    CollaborationRequest,
    CollaborationStatus,
    Creator,
    CreatorStatus,
    MatchProduct,
)
from app.models.reputation import Review
from app.services import reputation_service
from app.services.industry_taxonomy import INDUSTRY_CATEGORY, rollup

_MIN_COHORT = 3   # don't show a benchmark computed off too few peers to be meaningful


def _verdict(you: float, cohort_avg: float) -> str:
    if cohort_avg <= 0:
        return "on_par"
    if you >= cohort_avg * 1.1:
        return "above"
    if you <= cohort_avg * 0.9:
        return "below"
    return "on_par"


# --- Own-subject metrics ----------------------------------------------------
async def _subject_metrics(db: AsyncSession, *, subject_type: str, subject_id: uuid.UUID,
                           account_id: uuid.UUID, now) -> dict:
    S = CollaborationStatus
    rows = (await db.execute(
        select(CollaborationRequest.status, CollaborationRequest.initiator_account_id,
               CollaborationRequest.recipient_account_id, CollaborationRequest.expires_at).where(
            (CollaborationRequest.initiator_account_id == account_id)
            | (CollaborationRequest.recipient_account_id == account_id),
            CollaborationRequest.deleted_at.is_(None))
    )).all()
    received_actionable = responded = accepted = sent = 0
    for row in rows:
        is_recipient = row.recipient_account_id == account_id
        is_initiator = row.initiator_account_id == account_id
        answered = row.status in (S.accepted, S.declined)
        ghosted = row.status == S.expired or (
            row.status == S.pending and row.expires_at is not None and row.expires_at < now)
        if is_recipient and (answered or ghosted):
            received_actionable += 1
            if answered:
                responded += 1
            if row.status == S.accepted:
                accepted += 1
        if is_initiator and row.status != S.pending:
            sent += 1

    subject_col = Review.subject_creator_id if subject_type == "creator" else Review.subject_product_id
    avg_row = (await db.execute(
        select(func.count(), func.avg(Review.rating)).where(
            subject_col == subject_id, Review.deleted_at.is_(None))
    )).one()
    review_count, avg_rating = int(avg_row[0]), avg_row[1]

    return {
        "requests_received": received_actionable,
        "response_rate": (responded / received_actionable) if received_actionable else None,
        "acceptance_rate": (accepted / received_actionable) if received_actionable else None,
        "requests_sent": sent,
        "review_count": review_count,
        "avg_rating": round(float(avg_rating), 2) if avg_rating is not None else None,
    }


# --- Cohort benchmarks (creators) -------------------------------------------
async def engagement_benchmark(db: AsyncSession, creator: Creator) -> dict | None:
    """Engagement-rate benchmark for this creator: RevOS's own peer cohort
    when there's enough data (>= _MIN_COHORT), else the curated third-party
    industry-report figure (BM1/BM2) as a fallback — never both, and every
    result is explicitly tagged with which one it is. Shared by the private
    insights dashboard and the public creator page so the "cohort vs
    industry-report" decision lives in exactly one place."""
    if creator.engagement_rate is None:
        return None
    category = rollup(creator.industry)

    if category and creator.size_tier:
        slugs = [s for s, c in INDUSTRY_CATEGORY.items() if c == category]
        cohort = (
            Creator.industry.in_(slugs), Creator.size_tier == creator.size_tier,
            Creator.status == CreatorStatus.active, Creator.deleted_at.is_(None),
        )
        agg = (await db.execute(
            select(func.count(), func.avg(Creator.engagement_rate)).where(*cohort)
        )).one()
        cohort_size = int(agg[0])
        if cohort_size >= _MIN_COHORT and agg[1] is not None:
            avg_eng = float(agg[1])
            below = int((await db.execute(
                select(func.count()).where(*cohort, Creator.engagement_rate < creator.engagement_rate)
            )).scalar_one())
            return {
                "metric": "engagement_rate", "you": round(creator.engagement_rate, 4),
                "cohort_avg": round(avg_eng, 4), "cohort_size": cohort_size,
                "percentile": round(below / cohort_size * 100),
                "verdict": _verdict(creator.engagement_rate, avg_eng),
                "source": "revos_cohort", "citation": None,
            }

    if category:
        from app.services import benchmark_service
        row = await benchmark_service.get_current(
            db, industry_category=category, metric="engagement_rate", platform=creator.primary_platform)
        if row is not None:
            return {
                "metric": "engagement_rate", "you": round(creator.engagement_rate, 4),
                "cohort_avg": round(row.value, 4), "cohort_size": 0, "percentile": None,
                "verdict": _verdict(creator.engagement_rate, row.value),
                "source": "industry_report",
                "citation": f"{row.source} ({row.period_label})",
            }
    return None


async def _creator_cohort_benchmarks(db: AsyncSession, creator: Creator) -> list[dict]:
    benchmarks: list[dict] = []
    eng = await engagement_benchmark(db, creator)
    if eng is not None:
        benchmarks.append(eng)

    category = rollup(creator.industry)
    if category and creator.size_tier and creator.follower_count is not None:
        slugs = [s for s, c in INDUSTRY_CATEGORY.items() if c == category]
        cohort = (
            Creator.industry.in_(slugs), Creator.size_tier == creator.size_tier,
            Creator.status == CreatorStatus.active, Creator.deleted_at.is_(None),
        )
        agg = (await db.execute(
            select(func.count(), func.avg(Creator.follower_count)).where(*cohort)
        )).one()
        cohort_size = int(agg[0])
        # Follower count has no third-party-report equivalent to fall back to
        # — it stays RevOS-cohort-only.
        if cohort_size >= _MIN_COHORT and agg[1] is not None:
            benchmarks.append({
                "metric": "follower_count", "you": creator.follower_count,
                "cohort_avg": round(float(agg[1])), "cohort_size": cohort_size,
                "percentile": None, "verdict": _verdict(creator.follower_count, float(agg[1])),
                "source": "revos_cohort", "citation": None,
            })
    return benchmarks


# --- Collaboration workspace rollup (CW4) -----------------------------------
async def _collaboration_rollup(db: AsyncSession, *, subject_type: str, subject_id: uuid.UUID,
                                now) -> dict:
    """Per-collaboration outcomes for this subject — the workspace (Phase 5)
    feeding the dashboards (Phase 4), so a track record built there shows up
    here, not just raw follower/engagement numbers."""
    subject_col = (Collaboration.creator_id if subject_type == "creator"
                  else Collaboration.product_id)
    collabs = (await db.execute(select(Collaboration.id, Collaboration.state).where(
        subject_col == subject_id, Collaboration.deleted_at.is_(None)))).all()
    collab_ids = [c.id for c in collabs]
    total = len(collabs)
    active = sum(1 for c in collabs if c.state == CollaborationState.active)

    if not collab_ids:
        return {
            "collaborations_total": 0, "collaborations_active": 0,
            "published_assets": 0, "deliverables_total": 0,
            "deliverables_approved": 0, "deliverables_overdue": 0,
        }

    published_assets = int((await db.execute(select(func.count()).where(
        CollaborationAsset.collaboration_id.in_(collab_ids),
        CollaborationAsset.state == AssetState.published,
        CollaborationAsset.deleted_at.is_(None)))).scalar_one())

    deliverables = (await db.execute(select(
        CollaborationDeliverable.status, CollaborationDeliverable.due_at).where(
        CollaborationDeliverable.collaboration_id.in_(collab_ids),
        CollaborationDeliverable.deleted_at.is_(None)))).all()
    deliverables_total = len(deliverables)
    deliverables_approved = sum(1 for d in deliverables if d.status == DeliverableStatus.approved)
    deliverables_overdue = sum(
        1 for d in deliverables
        if d.status != DeliverableStatus.approved and d.due_at is not None and d.due_at < now)

    return {
        "collaborations_total": total, "collaborations_active": active,
        "published_assets": published_assets, "deliverables_total": deliverables_total,
        "deliverables_approved": deliverables_approved, "deliverables_overdue": deliverables_overdue,
    }


# --- Recommendations --------------------------------------------------------
def _rec(priority: str, title: str, detail: str) -> dict:
    return {"priority": priority, "title": title, "detail": detail}


def _recommendations(*, is_creator: bool, discoverable: bool, reputation, metrics: dict,
                     benchmarks: list[dict], verified_certs: int) -> list[dict]:
    recs: list[dict] = []

    if not discoverable:
        recs.append(_rec("high", "Turn on discoverability",
                         "You're hidden from the marketplace — opt in to start receiving requests."))

    rr = metrics["response_rate"]
    if rr is not None and rr < 0.7:
        recs.append(_rec("high", "Respond to more requests",
                         f"You've answered {rr * 100:.0f}% of requests — ghosting is the biggest drag "
                         "on your reliability score. Aim for 90%+."))

    if metrics["review_count"] == 0:
        recs.append(_rec("high", "Earn your first reviews",
                         "Complete a collaboration and prompt both sides to review — reviews are the "
                         "strongest reputation signal, and you have none yet."))

    if reputation.coverage < 0.5:
        recs.append(_rec("medium", "Build a track record",
                         f"Your reputation is provisional ({reputation.coverage * 100:.0f}% data coverage). "
                         "More collaborations and reviews will firm it up."))

    if verified_certs == 0:
        recs.append(_rec("medium", "Add a verified certification",
                         "Certifications are your weakest reputation signal. A verified credential "
                         "lifts trust for partners deciding whether to work with you."))

    eng = next((b for b in benchmarks if b["metric"] == "engagement_rate"), None)
    if eng:
        if eng["verdict"] == "above":
            recs.append(_rec("low", "Lean into your engagement",
                             f"Your engagement beats {eng['percentile']}% of peers in your cohort — "
                             "make it prominent when you pitch."))
        elif eng["verdict"] == "below":
            recs.append(_rec("medium", "Engagement is below your peers",
                             f"You're at {eng['you'] * 100:.1f}% vs a cohort average of "
                             f"{eng['cohort_avg'] * 100:.1f}%. More interactive content helps."))

    overdue = metrics.get("deliverables_overdue", 0)
    if overdue:
        recs.append(_rec("high", "You have overdue deliverables",
                         f"{overdue} deliverable{'s are' if overdue != 1 else ' is'} past its due date "
                         "in an active collaboration — missed deadlines hurt reliability."))

    if metrics.get("collaborations_total", 0) > 0 and metrics.get("published_assets", 0) == 0:
        recs.append(_rec("medium", "Get a draft over the finish line",
                         "You have collaborations underway but nothing published yet — draft and "
                         "approve a post to start building a real track record."))

    return recs


# --- Orchestration ----------------------------------------------------------
async def creator_insights(db: AsyncSession, creator: Creator, *, now) -> dict:
    rep = await reputation_service.reputation_for(
        db, subject_type="creator", subject_id=creator.id, account_id=creator.account_id, now=now)
    inputs = await reputation_service.gather_reputation_inputs(
        db, subject_type="creator", subject_id=creator.id, account_id=creator.account_id, now=now)
    metrics = await _subject_metrics(
        db, subject_type="creator", subject_id=creator.id, account_id=creator.account_id, now=now)
    metrics["engagement_rate"] = creator.engagement_rate
    metrics["follower_count"] = creator.follower_count
    metrics.update(await _collaboration_rollup(
        db, subject_type="creator", subject_id=creator.id, now=now))
    benchmarks = await _creator_cohort_benchmarks(db, creator)
    recs = _recommendations(is_creator=True, discoverable=creator.discoverable, reputation=rep,
                            metrics=metrics, benchmarks=benchmarks, verified_certs=inputs.verified_certs)
    return {
        "subject": {"id": str(creator.id), "type": "creator", "name": creator.display_name,
                    "industry": creator.industry, "industry_category": rollup(creator.industry),
                    "size_tier": creator.size_tier},
        "reputation": rep.as_dict(), "metrics": metrics,
        "benchmarks": benchmarks, "recommendations": recs,
    }


async def product_insights(db: AsyncSession, product: MatchProduct, *, now) -> dict:
    rep = await reputation_service.reputation_for(
        db, subject_type="match_product", subject_id=product.id, account_id=product.account_id, now=now)
    inputs = await reputation_service.gather_reputation_inputs(
        db, subject_type="match_product", subject_id=product.id, account_id=product.account_id, now=now)
    metrics = await _subject_metrics(
        db, subject_type="match_product", subject_id=product.id, account_id=product.account_id, now=now)
    metrics.update(await _collaboration_rollup(
        db, subject_type="product", subject_id=product.id, now=now))
    recs = _recommendations(is_creator=False, discoverable=product.discoverable, reputation=rep,
                            metrics=metrics, benchmarks=[], verified_certs=inputs.verified_certs)
    return {
        "subject": {"id": str(product.id), "type": "product", "name": product.name,
                    "industry": product.industry, "industry_category": rollup(product.industry),
                    "size_tier": None},
        "reputation": rep.as_dict(), "metrics": metrics,
        "benchmarks": [], "recommendations": recs,
    }
