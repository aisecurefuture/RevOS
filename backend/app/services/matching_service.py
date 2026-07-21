"""AI Matching Engine — score creators against products (Phase 3, M2).

Four transparent, independently-weighted dimensions, each 0–100:

  audience_fit         creator's niche/topics ↔ the product's audience interests
  engagement           engagement rate, normalized against a benchmark
  demographics         creator's audience age/gender/location ↔ the target spec
  brand_compatibility  creator's content/category ↔ the product's brand identity

Every function here is PURE — it reads plain attributes off the Creator and
MatchProduct objects (or any object with the same attributes) and does no I/O.
That keeps scoring fast, free, and deterministic for tests. An optional AI layer
can later refine ``brand_compatibility`` and the rationale (see ``ai_hook``), but
the baseline never depends on it.

Dimensions with no data on either side are marked ``available=False`` and are
excluded from the overall (the remaining weights renormalize), so a creator
isn't punished for a metric nobody supplied — we just report lower coverage.
"""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field

from app.services.industry_taxonomy import rollup, size_tier_for  # noqa: F401 (re-export)

# Default dimension weights. Sum need not be 1 — the overall renormalizes over
# whatever dimensions are available.
DEFAULT_WEIGHTS: dict[str, float] = {
    "audience_fit": 0.35,
    "engagement": 0.20,
    "demographics": 0.25,
    "brand_compatibility": 0.20,
}

# Engagement rate (0..1) that maps to a perfect 100. 6% is strong across most
# platforms; tune per-vertical later.
ENGAGEMENT_TARGET = 0.06

_AGE_BUCKETS_HINT = ("13-17", "18-24", "25-34", "35-44", "45-54", "55-64", "65+")


@dataclass
class DimensionScore:
    key: str
    score: float           # 0..100
    weight: float
    available: bool
    detail: str


@dataclass
class MatchScore:
    overall: float                       # 0..100, renormalized over available dims
    coverage: float                      # fraction of weight that had real data (0..1)
    dimensions: list[DimensionScore] = field(default_factory=list)
    rationale: str = ""

    def as_dict(self) -> dict:
        return {
            "overall": round(self.overall, 1),
            "coverage": round(self.coverage, 2),
            "rationale": self.rationale,
            "dimensions": [asdict(d) | {"score": round(d.score, 1)} for d in self.dimensions],
        }


# --- Text helpers -----------------------------------------------------------
def _tokens(text: str | None) -> set[str]:
    if not text:
        return set()
    return {t for t in re.split(r"[^a-z0-9]+", text.lower()) if len(t) > 1}


def _terms(values: list[str | None]) -> list[str]:
    return [v.strip().lower() for v in values if v and v.strip()]


def _term_matches(term: str, others: list[str]) -> bool:
    """A product term is 'covered' by a creator term if either contains the
    other, or they share a meaningful word token."""
    tt = _tokens(term)
    for o in others:
        ol = o.lower()
        if term in ol or ol in term:
            return True
        if tt & _tokens(o):
            return True
    return False


# --- Industry affinity ------------------------------------------------------
def _affinity_map(obj) -> dict[str, float]:
    """Normalized {slug: weight} from an object's weighted ``industries`` list,
    falling back to its scalar ``industry``. Weights sum to 1."""
    m: dict[str, float] = {}
    for e in getattr(obj, "industries", None) or []:
        raw = e if isinstance(e, dict) else (e.model_dump() if hasattr(e, "model_dump") else {})
        slug = (raw.get("industry") or "").strip().lower()
        if slug:
            m[slug] = m.get(slug, 0.0) + float(raw.get("weight", 1.0) or 0.0)
    if not m:
        scalar = getattr(obj, "industry", None)
        if scalar:
            m[scalar.strip().lower()] = 1.0
    total = sum(m.values())
    return {k: v / total for k, v in m.items()} if total > 0 else {}


def industry_overlap(creator, product) -> float | None:
    """Weighted industry alignment (0..1). Same slug = full credit; same rollup
    category (e.g. real_estate_agent ↔ interior_designer) = half credit.
    Returns None when neither side declares an industry."""
    c, p = _affinity_map(creator), _affinity_map(product)
    if not c or not p:
        return None
    total = 0.0
    for cs, cw in c.items():
        rc = rollup(cs)
        for ps, pw in p.items():
            if cs == ps:
                sim = 1.0
            elif rc and rc == rollup(ps):
                sim = 0.5
            else:
                sim = 0.0
            total += cw * pw * sim
    return max(0.0, min(1.0, total))


# --- Age-bucket math --------------------------------------------------------
def _parse_bucket(label: str) -> tuple[int, int] | None:
    label = label.strip()
    try:
        if label.endswith("+"):
            return (int(label[:-1]), 120)
        if "-" in label:
            lo, hi = label.split("-", 1)
            return (int(lo), int(hi))
        n = int(label)
        return (n, n)
    except ValueError:
        return None


def _age_in_target(age_dist: dict, tmin: int | None, tmax: int | None) -> float | None:
    """Share (0..1) of the audience whose age falls in [tmin, tmax], summing
    proportional overlap across buckets."""
    if not age_dist:
        return None
    lo_t = tmin if tmin is not None else 0
    hi_t = tmax if tmax is not None else 120
    total = 0.0
    for label, share in age_dist.items():
        rng = _parse_bucket(str(label))
        if rng is None:
            continue
        lo, hi = rng
        overlap = max(0, min(hi, hi_t) - max(lo, lo_t) + 1)
        span = (hi - lo + 1) or 1
        total += float(share) * (overlap / span)
    return max(0.0, min(1.0, total))


# --- Dimension scorers ------------------------------------------------------
def score_audience_fit(creator, product) -> DimensionScore:
    ta = product.target_audience or {}
    product_terms = _terms([product.category, *(ta.get("interests") or [])])
    creator_terms = _terms([creator.category, *(creator.topics or [])])
    if not product_terms:
        return DimensionScore("audience_fit", 55.0, DEFAULT_WEIGHTS["audience_fit"], False,
                              "No product category/interests to match against.")
    if not creator_terms:
        return DimensionScore("audience_fit", 0.0, DEFAULT_WEIGHTS["audience_fit"], False,
                              "Creator has no category/topics recorded.")
    matched = [t for t in product_terms if _term_matches(t, creator_terms)]
    coverage = len(matched) / len(product_terms)
    detail = (f"Matches {len(matched)}/{len(product_terms)} audience interests "
              f"({', '.join(matched) or 'none'}).")
    return DimensionScore("audience_fit", coverage * 100, DEFAULT_WEIGHTS["audience_fit"], True, detail)


def score_engagement(creator) -> DimensionScore:
    er = creator.engagement_rate
    if er is None:
        return DimensionScore("engagement", 0.0, DEFAULT_WEIGHTS["engagement"], False,
                              "No engagement rate recorded.")
    score = min(100.0, (er / ENGAGEMENT_TARGET) * 100)
    detail = f"Engagement rate {er * 100:.1f}% (vs {ENGAGEMENT_TARGET * 100:.0f}% benchmark)."
    return DimensionScore("engagement", score, DEFAULT_WEIGHTS["engagement"], True, detail)


def score_demographics(creator, product) -> DimensionScore:
    demo = creator.demographics or {}
    ta = product.target_audience or {}
    parts: list[float] = []
    notes: list[str] = []

    age = demo.get("age")
    if age and (ta.get("age_min") is not None or ta.get("age_max") is not None):
        share = _age_in_target(age, ta.get("age_min"), ta.get("age_max"))
        if share is not None:
            parts.append(share * 100)
            notes.append(f"{share * 100:.0f}% in target age band")

    gender = demo.get("gender")
    skew = ta.get("gender_skew")
    if gender and skew:
        if skew in ("female", "male"):
            s = float(gender.get(skew, 0.0))
            parts.append(s * 100)
            notes.append(f"{s * 100:.0f}% {skew}")
        elif skew == "balanced":
            f = float(gender.get("female", 0.0))
            m = float(gender.get("male", 0.0))
            s = (1 - abs(f - m)) * 100
            parts.append(s)
            notes.append("gender balance " + f"{s:.0f}")

    locs = demo.get("locations")
    targets = [t.lower() for t in (ta.get("locations") or [])]
    if locs and targets:
        matched_shares = [
            float(loc.get("share", 0.0)) for loc in locs
            if any(t in loc.get("name", "").lower() or loc.get("name", "").lower() in t for t in targets)
        ]
        s = (max(matched_shares) if matched_shares else 0.0) * 100
        parts.append(s)
        notes.append(f"{s:.0f}% in target locations")

    if not parts:
        return DimensionScore("demographics", 0.0, DEFAULT_WEIGHTS["demographics"], False,
                              "No overlapping demographic data to compare.")
    return DimensionScore("demographics", sum(parts) / len(parts),
                          DEFAULT_WEIGHTS["demographics"], True, "; ".join(notes) + ".")


def score_brand_compatibility(creator, product) -> DimensionScore:
    """Content/brand alignment. Prefers the normalized industry overlap (the
    strong, taxonomy-backed signal); falls back to free-text category matching
    when neither side declares an industry. ``ai_hook`` can refine later."""
    w = DEFAULT_WEIGHTS["brand_compatibility"]
    creator_terms = _terms([creator.category, *(creator.topics or [])])
    desc_terms = _terms([product.category]) + list(_tokens(product.description))
    overlap = [t for t in desc_terms if creator_terms and _term_matches(t, creator_terms)]
    topic_overlap = len(overlap) / len(desc_terms) if desc_terms else 0.0

    io = industry_overlap(creator, product)
    if io is not None:
        score = (0.6 * io + 0.4 * min(1.0, topic_overlap)) * 100
        detail = f"Industry overlap {io * 100:.0f}%; content overlap {topic_overlap * 100:.0f}%."
        return DimensionScore("brand_compatibility", score, w, True, detail)

    # No industry on either side — fall back to category matching.
    if not product.category:
        return DimensionScore("brand_compatibility", 55.0, w, False,
                              "No industry or product category to judge brand fit.")
    if not creator_terms:
        return DimensionScore("brand_compatibility", 0.0, w, False,
                              "Creator has no industry/category/topics recorded.")
    pcat = product.category.strip().lower()
    cat_match = 1.0 if (creator.category and creator.category.strip().lower() == pcat) \
        or _term_matches(pcat, creator_terms) else 0.0
    score = (0.6 * cat_match + 0.4 * min(1.0, topic_overlap)) * 100
    detail = f"Category {'aligned' if cat_match else 'differs'}; content overlap {topic_overlap * 100:.0f}%."
    return DimensionScore("brand_compatibility", score, w, True, detail)


# --- Orchestration ----------------------------------------------------------
def score_match(creator, product, weights: dict[str, float] | None = None) -> MatchScore:
    w = {**DEFAULT_WEIGHTS, **(weights or {})}
    dims = [
        score_audience_fit(creator, product),
        score_engagement(creator),
        score_demographics(creator, product),
        score_brand_compatibility(creator, product),
    ]
    for d in dims:
        d.weight = w.get(d.key, d.weight)

    avail = [d for d in dims if d.available]
    total_w = sum(d.weight for d in avail)
    overall = sum(d.score * d.weight for d in avail) / total_w if total_w else 0.0
    coverage = total_w / sum(d.weight for d in dims) if dims else 0.0
    return MatchScore(overall=overall, coverage=coverage, dimensions=dims,
                      rationale=build_rationale(overall, dims))


def build_rationale(overall: float, dims: list[DimensionScore]) -> str:
    avail = [d for d in dims if d.available]
    if not avail:
        return "Not enough data to score this match — add audience metrics to the creator."
    label = ("Strong match" if overall >= 75 else "Solid match" if overall >= 55
             else "Weak match" if overall >= 35 else "Poor match")
    ranked = sorted(avail, key=lambda d: d.score, reverse=True)
    pretty = {"audience_fit": "audience fit", "engagement": "engagement",
              "demographics": "demographics", "brand_compatibility": "brand compatibility"}
    top = ranked[0]
    parts = [f"{label} ({overall:.0f}/100). Strongest on {pretty[top.key]} — {top.detail}"]
    weakest = ranked[-1]
    if len(ranked) > 1 and weakest.score < 50:
        parts.append(f"Weakest on {pretty[weakest.key]}: {weakest.detail}")
    missing = [d for d in dims if not d.available]
    if missing:
        parts.append("Not scored (no data): " + ", ".join(pretty[d.key] for d in missing) + ".")
    return " ".join(parts)


def rank_creators(product, creators, weights: dict[str, float] | None = None) -> list[tuple]:
    """Return [(creator, MatchScore), ...] ranked best-first for one product."""
    scored = [(c, score_match(c, product, weights)) for c in creators]
    scored.sort(key=lambda pair: pair[1].overall, reverse=True)
    return scored


def rank_products(creator, products, weights: dict[str, float] | None = None) -> list[tuple]:
    """Return [(product, MatchScore), ...] ranked best-first for one creator."""
    scored = [(p, score_match(creator, p, weights)) for p in products]
    scored.sort(key=lambda pair: pair[1].overall, reverse=True)
    return scored
