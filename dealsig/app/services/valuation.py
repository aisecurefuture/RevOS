from dataclasses import dataclass
from decimal import Decimal, InvalidOperation

import httpx

from app.config import get_settings


@dataclass(frozen=True)
class Valuation:
    value: Decimal
    confidence: str
    provider_reference: str


def estimate_market_value(
    *, address: str, city: str, state: str, postal_code: str
) -> Valuation | None:
    """Call an optional licensed AVM through a deliberately small provider-neutral contract.

    Expected JSON response: {"value": 250000, "confidence": "medium", "id": "..."}.
    When no provider is configured, live records remain visibly unscored.
    """
    settings = get_settings()
    if not settings.market_data_api_url or not settings.market_data_api_key or not address:
        return None
    if settings.app_env == "production" and not settings.market_data_api_url.startswith("https://"):
        raise RuntimeError("MARKET_DATA_API_URL must use HTTPS in production")
    response = httpx.get(
        settings.market_data_api_url,
        params={
            "address": address,
            "city": city,
            "state": state,
            "postal_code": postal_code,
        },
        headers={"Authorization": f"Bearer {settings.market_data_api_key}"},
        timeout=settings.http_timeout_seconds,
        follow_redirects=False,
    )
    response.raise_for_status()
    payload = response.json()
    try:
        value = Decimal(str(payload["value"]))
    except (KeyError, InvalidOperation, TypeError) as exc:
        raise ValueError("Valuation provider returned an invalid value") from exc
    if value <= 0 or value > Decimal("1000000000"):
        raise ValueError("Valuation provider returned an out-of-range value")
    confidence = str(payload.get("confidence", "low")).lower()
    if confidence not in {"high", "medium", "low"}:
        confidence = "low"
    return Valuation(
        value=value,
        confidence=confidence,
        provider_reference=str(payload.get("id", ""))[:255],
    )

