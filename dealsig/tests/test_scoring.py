from decimal import Decimal

import pytest

from app.services.scoring import analyze_deal


def test_flip_analysis_uses_conservative_costs():
    result = analyze_deal(
        acquisition_cost=100_000,
        market_value=250_000,
        repairs=50_000,
        confidence="medium",
        instrument_type="direct_sale",
        days_remaining=10,
    )

    assert result.transaction_and_carry == Decimal("20000.00")
    assert result.contingency == Decimal("7500.00")
    assert result.all_in_cost == Decimal("177500.00")
    assert result.estimated_profit == Decimal("72500.00")
    assert 0 <= result.score <= 100
    assert result.factors["not_a_guarantee"] is True


def test_tax_lien_is_not_scored_as_a_flip():
    result = analyze_deal(
        acquisition_cost=5_000,
        market_value=200_000,
        repairs=40_000,
        other_costs=3_000,
        confidence="low",
        instrument_type="tax_lien",
    )

    assert result.repairs == Decimal("0.00")
    assert result.factors["model"] == "illinois_tax_lien_redemption_v1"
    assert "not ownership" in result.factors["warning"]
    assert result.score <= 85


def test_negative_inputs_are_rejected():
    with pytest.raises(ValueError):
        analyze_deal(acquisition_cost=-1, market_value=1)

