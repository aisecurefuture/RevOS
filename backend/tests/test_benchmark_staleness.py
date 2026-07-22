"""BM4 — staleness flag: a nudge to check for a fresher report, computed on
read (no new background job / notification channel needed)."""

from __future__ import annotations

from datetime import timedelta

import pytest
from app.models.base import utcnow
from app.schemas.benchmark import STALE_AFTER_DAYS, IndustryBenchmarkOut


def _row(*, days_old: int):
    class _Fake:
        pass

    import uuid
    f = _Fake()
    f.id = uuid.uuid4()
    f.industry_category = "real_estate"
    f.platform = "all"
    f.metric = "engagement_rate"
    f.value = 0.02
    f.source = "x"
    f.source_url = None
    f.period_label = "2026"
    f.updated_by_user_id = uuid.uuid4()
    f.updated_at = utcnow() - timedelta(days=days_old)
    return f


def test_fresh_benchmark_is_not_stale():
    out = IndustryBenchmarkOut.model_validate(_row(days_old=10))
    assert out.is_stale is False


def test_benchmark_past_threshold_is_stale():
    out = IndustryBenchmarkOut.model_validate(_row(days_old=STALE_AFTER_DAYS + 1))
    assert out.is_stale is True


def test_benchmark_exactly_at_threshold_is_stale():
    out = IndustryBenchmarkOut.model_validate(_row(days_old=STALE_AFTER_DAYS))
    assert out.is_stale is True


def test_benchmark_one_day_under_threshold_is_not_stale():
    out = IndustryBenchmarkOut.model_validate(_row(days_old=STALE_AFTER_DAYS - 1))
    assert out.is_stale is False
