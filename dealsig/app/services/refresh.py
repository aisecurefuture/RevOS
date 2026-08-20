from __future__ import annotations

import hashlib
import json
from datetime import datetime, timedelta, timezone
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Listing, RefreshRun, SourceStatus
from app.services.scoring import analyze_deal
from app.services.sources import SOURCE_BY_SLUG, SOURCES, ParsedListing, fetch_source
from app.services.valuation import estimate_market_value


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def ensure_sources(db: Session) -> None:
    for definition in SOURCES:
        status = db.get(SourceStatus, definition.slug)
        if not status:
            status = SourceStatus(
                slug=definition.slug,
                name=definition.name,
                official_url=definition.url,
                source_type=definition.source_type,
                refresh_interval_minutes=definition.interval_minutes,
            )
            db.add(status)
        else:
            status.name = definition.name
            status.official_url = definition.url
            status.source_type = definition.source_type
    db.commit()


def _fingerprint(record: ParsedListing) -> str:
    relevant = {
        "title": record.title,
        "status": record.status,
        "current_bid": str(record.current_bid),
        "auction_end": record.auction_end.isoformat() if record.auction_end else "",
        "description": record.description,
    }
    return hashlib.sha256(json.dumps(relevant, sort_keys=True).encode()).hexdigest()


def _score_listing(listing: Listing) -> None:
    price = listing.current_bid or listing.starting_bid
    if price is None or listing.estimated_market_value is None:
        listing.deal_score = 0
        listing.confidence = "unscored"
        listing.score_factors = {
            "reason": "Needs a verified acquisition price and market-value estimate",
            "not_a_guarantee": True,
        }
        return
    days_remaining = None
    if listing.auction_end:
        remaining = listing.auction_end - utcnow()
        days_remaining = remaining.days
    result = analyze_deal(
        acquisition_cost=price,
        market_value=listing.estimated_market_value,
        repairs=listing.repair_estimate,
        other_costs=listing.other_costs,
        confidence=listing.confidence if listing.confidence in {"high", "medium", "low"} else "low",
        instrument_type=listing.instrument_type,
        days_remaining=days_remaining,
    )
    listing.estimated_profit = result.estimated_profit
    listing.profit_margin = result.profit_margin
    listing.deal_score = result.score
    listing.score_factors = result.factors


def upsert_records(db: Session, source_slug: str, records: list[ParsedListing]) -> tuple[int, int]:
    created = 0
    updated = 0
    valuations_requested = 0
    now = utcnow()
    for record in records:
        listing = db.scalar(
            select(Listing).where(
                Listing.source == source_slug,
                Listing.external_id == record.external_id,
            )
        )
        incoming_fingerprint = _fingerprint(record)
        is_new = listing is None
        if is_new:
            listing = Listing(
                source=source_slug,
                external_id=record.external_id,
                title=record.title,
                source_url=record.source_url,
                confidence="low",
            )
            db.add(listing)
            created += 1
        else:
            old_fingerprint = listing.raw_data.get("fingerprint", "") if listing.raw_data else ""
            if old_fingerprint != incoming_fingerprint:
                listing.source_changed_at = now
                updated += 1
        for field in (
            "title",
            "description",
            "address",
            "city",
            "state",
            "postal_code",
            "county",
            "property_type",
            "instrument_type",
            "status",
            "auction_start",
            "auction_end",
            "current_bid",
            "starting_bid",
            "deposit_amount",
            "source_url",
            "contact_name",
            "contact_email",
            "contact_phone",
            "how_to_buy",
            "due_diligence",
        ):
            setattr(listing, field, getattr(record, field))
        listing.raw_data = {**record.raw_data, "fingerprint": incoming_fingerprint}
        listing.last_seen_at = now
        if (
            (is_new or listing.estimated_market_value is None)
            and record.address
            and valuations_requested < 10
        ):
            valuations_requested += 1
            try:
                valuation = estimate_market_value(
                    address=record.address,
                    city=record.city,
                    state=record.state,
                    postal_code=record.postal_code,
                )
                if valuation:
                    listing.estimated_market_value = valuation.value
                    listing.confidence = valuation.confidence
                    listing.raw_data = {
                        **listing.raw_data,
                        "valuation_provider_reference": valuation.provider_reference,
                    }
            except Exception as exc:
                listing.raw_data = {
                    **listing.raw_data,
                    "valuation_error": f"{type(exc).__name__}: {str(exc)[:180]}",
                }
        _score_listing(listing)
    db.commit()
    return created, updated


def refresh_source(db: Session, source_slug: str, trigger: str = "scheduled") -> RefreshRun:
    definition = SOURCE_BY_SLUG.get(source_slug)
    if not definition:
        raise ValueError(f"Unknown source: {source_slug}")
    status = db.get(SourceStatus, source_slug)
    if not status:
        ensure_sources(db)
        status = db.get(SourceStatus, source_slug)
    run = RefreshRun(source=source_slug, trigger=trigger)
    db.add(run)
    db.commit()
    try:
        result = fetch_source(definition, status.etag)
        created, updated = upsert_records(db, source_slug, result.records)
        now = utcnow()

        # Compare the page hash instead of only storing it. Without this a
        # calendar_monitor can never fire, which made every monitor-only source
        # silently inert while still reporting success.
        changed = bool(
            result.content_hash
            and status.content_hash
            and status.content_hash != result.content_hash
        )
        if changed:
            status.last_change_at = now

        run.status = "succeeded"
        run.discovered = len(result.records)
        run.created = created
        run.updated = updated
        run.changed = changed
        status.last_success_at = now
        status.records_found = len(result.records)
        status.consecutive_failures = 0
        status.last_error = ""
        if result.etag:
            status.etag = result.etag
        if result.content_hash:
            status.content_hash = result.content_hash

        # Health has to distinguish "fetched fine" from "produced anything".
        # A feed that parses nothing is broken even though the HTTP call
        # succeeded; a monitor legitimately produces no listings, so calling it
        # "healthy" alongside real feeds overstated coverage.
        if definition.source_type == "listing_feed":
            if result.records or result.not_modified:
                status.health = "healthy"
            else:
                status.health = "degraded"
                status.last_error = (
                    "Fetched successfully but the parser produced no listings — "
                    "the page layout has probably changed."
                )
        else:
            status.health = "monitoring"
    except Exception as exc:
        # Store a bounded diagnostic; never store response bodies or credentials.
        run.status = "failed"
        run.error = f"{type(exc).__name__}: {str(exc)[:350]}"
        status.health = "degraded"
        status.consecutive_failures += 1
        status.last_error = run.error
    finally:
        completed = utcnow()
        run.completed_at = completed
        status.last_refresh_at = completed
        db.commit()
    return run


def refresh_all(
    db: Session, trigger: str = "scheduled", *, only_due: bool = False
) -> list[RefreshRun]:
    ensure_sources(db)
    results = []
    now = utcnow()
    for source in SOURCES:
        status = db.get(SourceStatus, source.slug)
        if not status or not status.enabled:
            continue
        last_refresh = status.last_refresh_at
        if last_refresh and not last_refresh.tzinfo:
            last_refresh = last_refresh.replace(tzinfo=timezone.utc)
        due = not last_refresh or now - last_refresh >= timedelta(
            minutes=status.refresh_interval_minutes
        )
        if not only_due or due:
            results.append(refresh_source(db, source.slug, trigger=trigger))
    return results


def rescore_listing(
    listing: Listing,
    *,
    acquisition_cost: Decimal,
    market_value: Decimal,
    repairs: Decimal,
    other_costs: Decimal,
) -> dict:
    return analyze_deal(
        acquisition_cost=acquisition_cost,
        market_value=market_value,
        repairs=repairs,
        other_costs=other_costs,
        confidence=listing.confidence if listing.confidence in {"high", "medium", "low"} else "low",
        instrument_type=listing.instrument_type,
    ).to_dict()
