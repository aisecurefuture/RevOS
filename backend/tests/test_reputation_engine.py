"""Reputation engine (RK2) — pure, deterministic scoring across the three
reputation dimensions, Bayesian shrinkage, recency weighting, and coverage."""

from __future__ import annotations

import pytest
from app.services import reputation_service as r
from app.services.reputation_service import (
    ReliabilityInput,
    ReputationInputs,
    ReviewInput,
)


def test_reviews_recency_weighted_and_shrunk():
    # All 5★ but recent → high, yet shrinkage keeps a 2-review subject below a
    # theoretical max because of the neutral prior.
    d = r.score_review_reputation([ReviewInput(5, 0), ReviewInput(5, 0)])
    assert d.available
    # shrunk = (3*3 + 5+5) / (3 + 2) = 19/5 = 3.8 → (3.8-1)/4*100 = 70
    assert d.score == pytest.approx(70, abs=0.5)


def test_more_reviews_move_closer_to_true_average():
    few = r.score_review_reputation([ReviewInput(5, 0)] * 2)
    many = r.score_review_reputation([ReviewInput(5, 0)] * 40)
    # Same perfect ratings, but higher volume shrinks less → higher score.
    assert many.score > few.score
    assert many.score > 90  # 40 fresh 5★ dominates the prior


def test_recency_decay_downweights_old_reviews():
    # One fresh 5★, one very old 1★ → recent dominates.
    fresh_heavy = r.score_review_reputation([ReviewInput(5, 0), ReviewInput(1, 720)])
    # Same two ratings but both fresh → the 1★ drags it down more.
    both_fresh = r.score_review_reputation([ReviewInput(5, 0), ReviewInput(1, 0)])
    assert fresh_heavy.score > both_fresh.score


def test_no_reviews_unavailable():
    assert r.score_review_reputation([]).available is False


def test_reliability_responsiveness_and_follow_through():
    d = r.score_reliability(ReliabilityInput(
        received_actionable=10, responded=9, initiated_resolved=4, withdrawn_by_subject=1))
    # responsiveness 0.9, follow_through 1 - 1/4 = 0.75 → mean 0.825 → 82.5
    assert d.available
    assert d.score == pytest.approx(82.5, abs=0.1)


def test_reliability_ghosting_tanks_score():
    ghost = r.score_reliability(ReliabilityInput(
        received_actionable=10, responded=2, initiated_resolved=0, withdrawn_by_subject=0))
    assert ghost.score == pytest.approx(20, abs=0.1)


def test_reliability_unavailable_without_history():
    assert r.score_reliability(None).available is False
    assert r.score_reliability(ReliabilityInput(0, 0, 0, 0)).available is False


def test_certifications_verified_worth_more():
    assert r.score_certifications(0, 0).available is False
    assert r.score_certifications(1, 0).score == pytest.approx(45)
    assert r.score_certifications(0, 1).score == pytest.approx(15)
    assert r.score_certifications(3, 0).score == pytest.approx(100)  # capped


def test_overall_renormalizes_and_reports_coverage():
    # Only reviews present — other two dimensions absent.
    res = r.score_reputation(ReputationInputs(reviews=[ReviewInput(5, 0)] * 40))
    assert res.coverage == pytest.approx(0.45, abs=0.001)  # only review weight available
    rev = next(d for d in res.dimensions if d.key == "review_reputation")
    assert res.overall == pytest.approx(rev.score, abs=0.1)  # renormalized to just reviews
    assert res.review_count == 40


def test_full_reputation_weighted_mean():
    res = r.score_reputation(ReputationInputs(
        reviews=[ReviewInput(5, 0)] * 20,
        verified_certs=2, unverified_certs=0,
        reliability=ReliabilityInput(10, 10, 5, 0),
    ))
    assert res.coverage == pytest.approx(1.0)
    by = {d.key: d.score for d in res.dimensions}
    expected = (by["review_reputation"] * 0.45 + by["reliability"] * 0.35
                + by["certifications"] * 0.20)
    assert res.overall == pytest.approx(expected, abs=0.1)
    assert "reputation" in res.rationale.lower()


def test_unproven_subject_reads_as_low_coverage_not_bad():
    res = r.score_reputation(ReputationInputs())
    assert res.overall == 0.0
    assert res.coverage == 0.0
    assert "unproven" in res.rationale.lower()


def test_as_dict_shape():
    d = r.score_reputation(ReputationInputs(reviews=[ReviewInput(4, 10)])).as_dict()
    assert set(d) == {"overall", "coverage", "review_count", "rationale", "dimensions"}
    assert {dd["key"] for dd in d["dimensions"]} == {
        "review_reputation", "reliability", "certifications"}
