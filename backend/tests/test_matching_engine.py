"""AI Matching Engine — deterministic scoring across the four dimensions."""

from __future__ import annotations

from types import SimpleNamespace

import pytest
from app.services import matching_service as m


def _creator(**over):
    base = dict(
        category="real_estate",
        topics=["real estate", "home decor"],
        engagement_rate=0.05,
        follower_count=50_000,
        avg_views=8_000,
        demographics={
            "age": {"18-24": 0.15, "25-34": 0.40, "35-44": 0.30, "45-54": 0.10, "55+": 0.05},
            "gender": {"female": 0.62, "male": 0.36, "other": 0.02},
            "locations": [{"name": "Austin, TX", "share": 0.25}, {"name": "US", "share": 0.80}],
        },
    )
    base.update(over)
    return SimpleNamespace(**base)


def _product(**over):
    base = dict(
        category="real_estate",
        description="Home buying platform for first-time buyers.",
        target_audience={
            "age_min": 25, "age_max": 44, "gender_skew": "female",
            "locations": ["Austin, TX", "US"], "interests": ["home buying", "interiors"],
        },
    )
    base.update(over)
    return SimpleNamespace(**base)


def test_audience_fit_partial_coverage():
    d = m.score_audience_fit(_creator(), _product())
    # product terms: real_estate, home buying, interiors → real_estate + home(buying) match, interiors doesn't
    assert d.available
    assert d.score == pytest.approx(2 / 3 * 100, abs=0.1)


def test_audience_fit_unavailable_without_product_terms():
    d = m.score_audience_fit(_creator(), _product(category=None, target_audience={}))
    assert d.available is False


def test_engagement_normalizes_to_benchmark():
    assert m.score_engagement(_creator(engagement_rate=0.06)).score == pytest.approx(100)
    assert m.score_engagement(_creator(engagement_rate=0.03)).score == pytest.approx(50)
    assert m.score_engagement(_creator(engagement_rate=0.12)).score == pytest.approx(100)  # capped
    off = m.score_engagement(_creator(engagement_rate=None))
    assert off.available is False and off.score == 0


def test_demographics_age_gender_location_average():
    d = m.score_demographics(_creator(), _product())
    # age in [25,44] = 0.40+0.30 = 0.70 → 70; female 0.62 → 62; location max 0.80 → 80
    assert d.available
    assert d.score == pytest.approx((70 + 62 + 80) / 3, abs=0.1)


def test_demographics_partial_age_bucket_overlap():
    # target [30,50] partially overlaps 25-34 (30-34 = 5/10) and 35-44 (full) and 45-54 (45-50 = 6/10)
    d = m.score_demographics(
        _creator(demographics={"age": {"25-34": 0.4, "35-44": 0.3, "45-54": 0.2}}),
        _product(target_audience={"age_min": 30, "age_max": 50}),
    )
    expected = (0.4 * 0.5 + 0.3 * 1.0 + 0.2 * 0.6) * 100
    assert d.score == pytest.approx(expected, abs=0.5)


def test_demographics_unavailable_when_no_overlap():
    d = m.score_demographics(_creator(demographics={}), _product())
    assert d.available is False


def test_brand_compatibility_aligned_beats_mismatched():
    aligned = m.score_brand_compatibility(_creator(), _product())
    mismatched = m.score_brand_compatibility(
        _creator(category="fitness", topics=["gym", "protein"]), _product())
    assert aligned.available and mismatched.available
    # Exact category match dominates the 0.6 term, so aligned clears the midpoint.
    assert aligned.score >= 60
    # No category or topic overlap → only the diluted secondary, well below.
    assert mismatched.score < 40
    assert aligned.score > mismatched.score


def test_score_match_overall_and_full_coverage():
    res = m.score_match(_creator(engagement_rate=0.06), _product())
    assert res.coverage == pytest.approx(1.0)
    # all four available; overall is the weighted mean
    by = {d.key: d.score for d in res.dimensions}
    expected = (by["audience_fit"] * 0.35 + by["engagement"] * 0.20
                + by["demographics"] * 0.25 + by["brand_compatibility"] * 0.20)
    assert res.overall == pytest.approx(expected, abs=0.1)
    assert "match" in res.rationale.lower()


def test_missing_dimensions_renormalize_and_lower_coverage():
    lean = _creator(engagement_rate=None, demographics={})
    res = m.score_match(lean, _product())
    # only audience_fit (0.35) + brand_compatibility (0.20) available
    assert res.coverage == pytest.approx(0.55, abs=0.001)
    avail = {d.key for d in res.dimensions if d.available}
    assert avail == {"audience_fit", "brand_compatibility"}
    # overall renormalized over the 0.55 of weight that had data
    a = next(d for d in res.dimensions if d.key == "audience_fit")
    b = next(d for d in res.dimensions if d.key == "brand_compatibility")
    assert res.overall == pytest.approx((a.score * 0.35 + b.score * 0.20) / 0.55, abs=0.1)


def test_rank_creators_orders_best_first():
    strong = _creator()
    weak = _creator(category="fitness", topics=["gym"], engagement_rate=0.005,
                    demographics={"gender": {"male": 0.9, "female": 0.1}})
    ranked = m.rank_creators(_product(), [weak, strong])
    assert [c for c, _ in ranked][0] is strong
    assert ranked[0][1].overall > ranked[1][1].overall


def test_industry_overlap_exact_rollup_and_none():
    def c(inds):
        return SimpleNamespace(industries=[{"industry": i, "weight": w} for i, w in inds], industry=None)
    # exact slug match
    assert m.industry_overlap(c([("real_estate_agent", 1)]), c([("real_estate_agent", 1)])) == pytest.approx(1.0)
    # same rollup category (real_estate), different slug → half credit
    assert m.industry_overlap(c([("real_estate_agent", 1)]), c([("interior_designer", 1)])) == pytest.approx(0.5)
    # different category → no credit
    assert m.industry_overlap(c([("real_estate_agent", 1)]), c([("fitness", 1)])) == pytest.approx(0.0)
    # missing on one side → None (unavailable)
    assert m.industry_overlap(c([]), c([("fitness", 1)])) is None


def test_industry_overlap_weighted_multi_affinity():
    creator = SimpleNamespace(
        industries=[{"industry": "real_estate_agent", "weight": 0.6},
                    {"industry": "interior_designer", "weight": 0.4}], industry=None)
    product = SimpleNamespace(industries=[{"industry": "real_estate_agent", "weight": 1.0}], industry=None)
    # 0.6*1*1 (exact) + 0.4*1*0.5 (same rollup) = 0.8
    assert m.industry_overlap(creator, product) == pytest.approx(0.8, abs=0.01)


def test_scalar_industry_falls_back_into_affinity():
    creator = SimpleNamespace(industries=[], industry="real_estate_agent")
    product = SimpleNamespace(industries=[], industry="real_estate_agent")
    assert m.industry_overlap(creator, product) == pytest.approx(1.0)


def test_brand_compat_prefers_industry_signal():
    creator = _creator(industry="real_estate_agent", industries=[])
    product = _product(industry="real_estate_agent", industries=[])
    d = m.score_brand_compatibility(creator, product)
    assert d.available and "Industry overlap" in d.detail
    assert d.score >= 60


def test_size_tier_boundaries():
    assert m.size_tier_for(None) is None
    assert m.size_tier_for(5_000) == "nano"
    assert m.size_tier_for(10_000) == "micro"
    assert m.size_tier_for(250_000) == "mid"
    assert m.size_tier_for(700_000) == "macro"
    assert m.size_tier_for(2_000_000) == "mega"


def test_as_dict_shape():
    d = m.score_match(_creator(), _product()).as_dict()
    assert set(d) == {"overall", "coverage", "rationale", "dimensions"}
    assert len(d["dimensions"]) == 4
    assert {dd["key"] for dd in d["dimensions"]} == {
        "audience_fit", "engagement", "demographics", "brand_compatibility"}
