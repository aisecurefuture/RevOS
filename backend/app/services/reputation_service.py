"""Reputation engine — brands, products, and creators (Phase 3, RK2).

The symmetric counterpart to the creator matching engine (matching_service):
a transparent, coverage-aware, rationale-driven 0-100 score. Where matching
scores a *pair's fit*, this scores a *subject's reputation* — and any subject
that gets reviewed (a brand's product, or a creator) earns one from three
signals:

  review_reputation   recency-weighted, Bayesian-shrunk average of reviews
  reliability         collaboration follow-through — responds, doesn't ghost
  certifications      verified trust credentials

Design mirrors M2 exactly: the scoring functions are PURE (aggregated inputs
in, no I/O), so they're deterministic and unit-testable; dimensions with no
data are ``available=False`` and drop out of the overall (remaining weights
renormalize), and ``coverage`` reports how much real signal backs the score —
so a brand new to the marketplace reads as *unproven*, not *bad*.

Two deliberate choices worth calling out:
- **Bayesian shrinkage** on the review average pulls low-volume subjects toward
  a neutral prior, so a single 5★ never outranks a proven 4.8-over-50.
- **Recency weighting** decays old reviews, so reputation reflects recent
  behavior, not ancient history.

``gather_reputation_inputs`` / ``reputation_for`` (async, bottom of file) build
the inputs from the database.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field

# --- Tunables ---------------------------------------------------------------
DEFAULT_WEIGHTS: dict[str, float] = {
    "review_reputation": 0.45,
    "reliability": 0.35,
    "certifications": 0.20,
}

# Bayesian shrinkage: like starting every subject with a few neutral reviews.
REVIEW_PRIOR_MEAN = 3.0        # neutral point on the 1-5 scale
REVIEW_PRIOR_WEIGHT = 3.0      # ~3 virtual neutral reviews of pull
REVIEW_HALFLIFE_DAYS = 180.0   # a review's weight halves every ~6 months

# Certifications: verified credentials are worth far more than self-reported.
CERT_VERIFIED_POINTS = 45.0
CERT_UNVERIFIED_POINTS = 15.0


@dataclass
class ReviewInput:
    rating: int          # 1..5
    age_days: float      # how old the review is, for recency weighting


@dataclass
class ReliabilityInput:
    received_actionable: int      # requests the subject should have answered
    responded: int                # ...of those, how many they answered (vs ghosted)
    initiated_resolved: int       # requests the subject sent that got resolved
    withdrawn_by_subject: int     # ...of those, how many they pulled back


@dataclass
class ReputationInputs:
    reviews: list[ReviewInput] = field(default_factory=list)
    verified_certs: int = 0
    unverified_certs: int = 0
    reliability: ReliabilityInput | None = None


@dataclass
class DimensionScore:
    key: str
    score: float
    weight: float
    available: bool
    detail: str


@dataclass
class ReputationScore:
    overall: float
    coverage: float
    review_count: int
    dimensions: list[DimensionScore] = field(default_factory=list)
    rationale: str = ""

    def as_dict(self) -> dict:
        return {
            "overall": round(self.overall, 1),
            "coverage": round(self.coverage, 2),
            "review_count": self.review_count,
            "rationale": self.rationale,
            "dimensions": [asdict(d) | {"score": round(d.score, 1)} for d in self.dimensions],
        }


# --- Dimension scorers ------------------------------------------------------
def score_review_reputation(reviews: list[ReviewInput]) -> DimensionScore:
    w = DEFAULT_WEIGHTS["review_reputation"]
    if not reviews:
        return DimensionScore("review_reputation", 0.0, w, False, "No reviews yet.")
    weighted_sum = 0.0
    weight_total = 0.0
    for r in reviews:
        rw = 0.5 ** (max(0.0, r.age_days) / REVIEW_HALFLIFE_DAYS)
        weighted_sum += rw * r.rating
        weight_total += rw
    raw_avg = weighted_sum / weight_total if weight_total else REVIEW_PRIOR_MEAN
    # Bayesian shrinkage toward the neutral prior.
    shrunk = (REVIEW_PRIOR_WEIGHT * REVIEW_PRIOR_MEAN + weighted_sum) / (REVIEW_PRIOR_WEIGHT + weight_total)
    score = (shrunk - 1) / 4 * 100
    detail = (f"{len(reviews)} review{'s' if len(reviews) != 1 else ''}, "
              f"recency-weighted {raw_avg:.1f}/5 (adjusted {shrunk:.1f}/5 for volume).")
    return DimensionScore("review_reputation", max(0.0, min(100.0, score)), w, True, detail)


def score_reliability(rel: ReliabilityInput | None) -> DimensionScore:
    w = DEFAULT_WEIGHTS["reliability"]
    if rel is None or (rel.received_actionable == 0 and rel.initiated_resolved == 0):
        return DimensionScore("reliability", 0.0, w, False, "No collaboration history yet.")
    parts: list[float] = []
    notes: list[str] = []
    if rel.received_actionable > 0:
        responsiveness = rel.responded / rel.received_actionable
        parts.append(responsiveness)
        notes.append(f"responded to {rel.responded}/{rel.received_actionable} requests")
    if rel.initiated_resolved > 0:
        follow_through = 1 - (rel.withdrawn_by_subject / rel.initiated_resolved)
        parts.append(follow_through)
        if rel.withdrawn_by_subject:
            notes.append(f"withdrew {rel.withdrawn_by_subject}/{rel.initiated_resolved} they sent")
    score = (sum(parts) / len(parts)) * 100
    return DimensionScore("reliability", score, w, True, "; ".join(notes) + "." if notes else "Established track record.")


def score_certifications(verified: int, unverified: int) -> DimensionScore:
    w = DEFAULT_WEIGHTS["certifications"]
    if verified == 0 and unverified == 0:
        return DimensionScore("certifications", 0.0, w, False, "No certifications on file.")
    score = min(100.0, verified * CERT_VERIFIED_POINTS + unverified * CERT_UNVERIFIED_POINTS)
    detail = f"{verified} verified" + (f", {unverified} self-reported" if unverified else "") + " certification(s)."
    return DimensionScore("certifications", score, w, True, detail)


# --- Orchestration ----------------------------------------------------------
def score_reputation(inputs: ReputationInputs) -> ReputationScore:
    dims = [
        score_review_reputation(inputs.reviews),
        score_reliability(inputs.reliability),
        score_certifications(inputs.verified_certs, inputs.unverified_certs),
    ]
    avail = [d for d in dims if d.available]
    total_w = sum(d.weight for d in avail)
    overall = sum(d.score * d.weight for d in avail) / total_w if total_w else 0.0
    coverage = total_w / sum(d.weight for d in dims) if dims else 0.0
    return ReputationScore(
        overall=overall, coverage=coverage, review_count=len(inputs.reviews),
        dimensions=dims, rationale=build_rationale(overall, coverage, dims),
    )


def build_rationale(overall: float, coverage: float, dims: list[DimensionScore]) -> str:
    avail = [d for d in dims if d.available]
    if not avail:
        return "Unproven — no reviews, collaboration history, or certifications yet."
    label = ("Excellent reputation" if overall >= 80 else "Strong reputation" if overall >= 60
             else "Mixed reputation" if overall >= 40 else "Weak reputation")
    pretty = {"review_reputation": "reviews", "reliability": "reliability",
              "certifications": "certifications"}
    top = max(avail, key=lambda d: d.score)
    parts = [f"{label} ({overall:.0f}/100). Strongest on {pretty[top.key]} — {top.detail}"]
    if coverage < 0.5:
        parts.append("Low coverage — still building a track record, so treat as provisional.")
    missing = [pretty[d.key] for d in dims if not d.available]
    if missing:
        parts.append("Not yet scored: " + ", ".join(missing) + ".")
    return " ".join(parts)


# --- DB aggregation ---------------------------------------------------------
async def gather_reputation_inputs(db, *, subject_type: str, subject_id, account_id, now) -> ReputationInputs:
    """Build ReputationInputs for a creator or product subject from stored
    reviews, certifications, and the subject account's collaboration behavior."""
    from sqlmodel import or_, select

    from app.models.matching import CollaborationRequest, CollaborationStatus
    from app.models.reputation import CertificationStatus, Certification, Review

    # Reviews about this subject.
    subject_col = Review.subject_creator_id if subject_type == "creator" else Review.subject_product_id
    review_rows = (await db.execute(
        select(Review.rating, Review.created_at).where(
            subject_col == subject_id, Review.deleted_at.is_(None))
    )).all()
    reviews = [
        ReviewInput(rating=r.rating, age_days=max(0.0, (now - r.created_at).total_seconds() / 86400.0))
        for r in review_rows
    ]

    # Certifications on this subject (active only).
    cert_rows = (await db.execute(
        select(Certification.verified).where(
            Certification.subject_type == subject_type, Certification.subject_id == subject_id,
            Certification.status == CertificationStatus.active, Certification.deleted_at.is_(None))
    )).all()
    verified = sum(1 for c in cert_rows if c.verified)
    unverified = len(cert_rows) - verified

    # Reliability from the subject account's collaboration behavior.
    S = CollaborationStatus
    cr_rows = (await db.execute(
        select(CollaborationRequest.status, CollaborationRequest.initiator_account_id,
               CollaborationRequest.recipient_account_id, CollaborationRequest.expires_at).where(
            or_(CollaborationRequest.initiator_account_id == account_id,
                CollaborationRequest.recipient_account_id == account_id),
            CollaborationRequest.deleted_at.is_(None))
    )).all()
    received_actionable = responded = initiated_resolved = withdrawn = 0
    for row in cr_rows:
        is_recipient = row.recipient_account_id == account_id
        is_initiator = row.initiator_account_id == account_id
        answered = row.status in (S.accepted, S.declined)
        ghosted = row.status == S.expired or (
            row.status == S.pending and row.expires_at is not None and row.expires_at < now)
        if is_recipient and (answered or ghosted):
            received_actionable += 1
            if answered:
                responded += 1
        if is_initiator and row.status in (S.accepted, S.declined, S.withdrawn):
            initiated_resolved += 1
            if row.status == S.withdrawn:
                withdrawn += 1

    reliability = ReliabilityInput(
        received_actionable=received_actionable, responded=responded,
        initiated_resolved=initiated_resolved, withdrawn_by_subject=withdrawn,
    )
    return ReputationInputs(reviews=reviews, verified_certs=verified,
                            unverified_certs=unverified, reliability=reliability)


async def reputation_for(db, *, subject_type: str, subject_id, account_id, now) -> ReputationScore:
    inputs = await gather_reputation_inputs(
        db, subject_type=subject_type, subject_id=subject_id, account_id=account_id, now=now)
    return score_reputation(inputs)
