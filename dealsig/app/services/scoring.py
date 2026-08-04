from dataclasses import asdict, dataclass
from decimal import ROUND_HALF_UP, Decimal

MONEY = Decimal("0.01")


@dataclass(frozen=True)
class DealAnalysis:
    acquisition_cost: Decimal
    resale_value: Decimal
    repairs: Decimal
    transaction_and_carry: Decimal
    contingency: Decimal
    all_in_cost: Decimal
    estimated_profit: Decimal
    profit_margin: Decimal
    score: int
    confidence: str
    factors: dict

    def to_dict(self) -> dict:
        result = asdict(self)
        for key, value in result.items():
            if isinstance(value, Decimal):
                result[key] = float(value)
        return result


def analyze_deal(
    *,
    acquisition_cost: Decimal | int | float | None,
    market_value: Decimal | int | float | None,
    repairs: Decimal | int | float | None = None,
    other_costs: Decimal | int | float | None = None,
    confidence: str = "low",
    instrument_type: str = "direct_sale",
    days_remaining: int | None = None,
) -> DealAnalysis:
    acquisition = Decimal(str(acquisition_cost or 0))
    resale = Decimal(str(market_value or 0))
    repair_cost = Decimal(str(repairs or 0))
    explicit_other = Decimal(str(other_costs or 0))

    if acquisition < 0 or resale < 0 or repair_cost < 0 or explicit_other < 0:
        raise ValueError("Deal inputs cannot be negative")

    if instrument_type == "tax_lien":
        return analyze_tax_lien(
            principal=acquisition,
            market_value=resale,
            other_costs=explicit_other,
            confidence=confidence,
            days_remaining=days_remaining,
        )

    transaction_and_carry = max(resale * Decimal("0.08"), explicit_other)
    contingency = repair_cost * Decimal("0.15")
    all_in = acquisition + repair_cost + transaction_and_carry + contingency
    profit = resale - all_in
    margin = (profit / resale * 100) if resale else Decimal("0")

    margin_component = max(0, min(55, int(float(margin) * 1.5)))
    spread_component = max(0, min(20, int(float(profit / Decimal("10000")))))
    confidence_adjustment = {"high": 12, "medium": 5, "low": -8}.get(confidence, -8)
    urgency_adjustment = 0
    if days_remaining is not None:
        urgency_adjustment = 6 if 3 <= days_remaining <= 21 else (-4 if days_remaining < 3 else 0)
    score = max(0, min(100, 20 + margin_component + spread_component + confidence_adjustment + urgency_adjustment))

    return DealAnalysis(
        acquisition_cost=acquisition.quantize(MONEY),
        resale_value=resale.quantize(MONEY),
        repairs=repair_cost.quantize(MONEY),
        transaction_and_carry=transaction_and_carry.quantize(MONEY),
        contingency=contingency.quantize(MONEY),
        all_in_cost=all_in.quantize(MONEY),
        estimated_profit=profit.quantize(MONEY),
        profit_margin=margin.quantize(Decimal("0.001"), rounding=ROUND_HALF_UP),
        score=score,
        confidence=confidence,
        factors={
            "model": "flip_v1",
            "transaction_and_carry_assumption": "8% of resale value, or supplied costs if higher",
            "repair_contingency": "15%",
            "not_a_guarantee": True,
        },
    )


def analyze_tax_lien(
    *,
    principal: Decimal,
    market_value: Decimal,
    other_costs: Decimal,
    confidence: str,
    days_remaining: int | None,
) -> DealAnalysis:
    # Illinois tax-sale returns depend on the winning penalty bid, redemption, statutory
    # notices, and court process. This conservative scenario is deliberately not an ARV flip.
    assumed_penalty_rate = Decimal("0.06")
    notice_and_legal_reserve = max(other_costs, Decimal("2500"))
    expected_redemption_return = principal * assumed_penalty_rate
    all_in = principal + notice_and_legal_reserve
    profit = expected_redemption_return - notice_and_legal_reserve
    margin = (profit / all_in * 100) if all_in else Decimal("0")
    collateral_ratio = (market_value / principal) if principal else Decimal("0")
    score = 20 + min(35, int(collateral_ratio)) + max(0, min(20, int(float(margin))))
    score += {"high": 10, "medium": 3, "low": -10}.get(confidence, -10)
    if days_remaining is not None and days_remaining < 7:
        score -= 5
    score = max(0, min(85, score))

    return DealAnalysis(
        acquisition_cost=principal.quantize(MONEY),
        resale_value=market_value.quantize(MONEY),
        repairs=Decimal("0.00"),
        transaction_and_carry=notice_and_legal_reserve.quantize(MONEY),
        contingency=Decimal("0.00"),
        all_in_cost=all_in.quantize(MONEY),
        estimated_profit=profit.quantize(MONEY),
        profit_margin=margin.quantize(Decimal("0.001"), rounding=ROUND_HALF_UP),
        score=score,
        confidence=confidence,
        factors={
            "model": "illinois_tax_lien_redemption_v1",
            "assumed_redemption_penalty": "6% scenario only",
            "legal_and_notice_reserve": float(notice_and_legal_reserve),
            "collateral_value_used_for_risk_only": float(market_value),
            "warning": "A tax-sale certificate is not ownership of the property.",
            "not_a_guarantee": True,
        },
    )

