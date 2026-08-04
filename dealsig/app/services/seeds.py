from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.models import Listing, User
from app.services.refresh import _score_listing, ensure_sources
from app.services.sources import SOURCE_BY_SLUG, STANDARD_DUE_DILIGENCE


def _now() -> datetime:
    return datetime.now(timezone.utc)


def seed_database(db: Session) -> None:
    settings = get_settings()
    ensure_sources(db)
    if settings.demo_mode:
        user = db.scalar(select(User).where(User.email == "demo@dealsig.ai"))
        if not user:
            db.add(
                User(
                    email="demo@dealsig.ai",
                    full_name="Demo Investor",
                    subscription_status="active",
                )
            )
            db.commit()
    count = db.scalar(select(func.count()).select_from(Listing)) or 0
    if count or not settings.seed_demo_data:
        return

    now = _now()
    samples = [
        {
            "source": "govdeals",
            "external_id": "DEMO-GD-1042",
            "title": "Brick bungalow · renovation scenario",
            "address": "South Shore preview · exact address for members",
            "city": "Chicago",
            "county": "Cook",
            "property_type": "single_family",
            "instrument_type": "direct_sale",
            "current_bid": Decimal("78500"),
            "estimated_market_value": Decimal("238000"),
            "repair_estimate": Decimal("62000"),
            "other_costs": Decimal("19040"),
            "auction_end": now + timedelta(days=4, hours=7),
            "confidence": "medium",
            "description": "Illustrative direct-auction scenario based on public-sale deal patterns. Verify the actual lot, condition, title, and seller terms.",
        },
        {
            "source": "treasury",
            "external_id": "DEMO-TR-2601",
            "title": "Two-flat · forfeiture sale scenario",
            "address": "West Side preview · exact address for members",
            "city": "Chicago",
            "county": "Cook",
            "property_type": "multi_family",
            "instrument_type": "direct_sale",
            "starting_bid": Decimal("145000"),
            "estimated_market_value": Decimal("365000"),
            "repair_estimate": Decimal("78000"),
            "auction_end": now + timedelta(days=11, hours=2),
            "confidence": "medium",
            "description": "Illustrative seized-property auction scenario. Treasury properties are sold as-is under property-specific terms.",
        },
        {
            "source": "gsa",
            "external_id": "DEMO-GSA-872",
            "title": "Former federal office · adaptive reuse scenario",
            "address": "Near Joliet · exact address for members",
            "city": "Joliet",
            "county": "Will",
            "property_type": "commercial",
            "instrument_type": "direct_sale",
            "current_bid": Decimal("310000"),
            "estimated_market_value": Decimal("690000"),
            "repair_estimate": Decimal("160000"),
            "auction_end": now + timedelta(days=18),
            "confidence": "low",
            "description": "Illustrative GSA reuse scenario. Zoning, environmental review, deed restrictions, and carrying time can dominate the economics.",
        },
        {
            "source": "fdic",
            "external_id": "DEMO-FDIC-81",
            "title": "Bank-owned ranch · broker offer scenario",
            "address": "Waukegan preview · exact address for members",
            "city": "Waukegan",
            "county": "Lake",
            "property_type": "single_family",
            "instrument_type": "broker_sale",
            "starting_bid": Decimal("132000"),
            "estimated_market_value": Decimal("265000"),
            "repair_estimate": Decimal("48000"),
            "auction_end": now + timedelta(days=22),
            "confidence": "medium",
            "description": "Illustrative FDIC broker-offer scenario. FDIC properties are generally sold as-is and offers are evaluated on multiple terms.",
        },
        {
            "source": "cook_county",
            "external_id": "DEMO-COOK-PIN",
            "title": "Residential tax-lien certificate scenario",
            "address": "Cook County parcel preview",
            "city": "Chicago",
            "county": "Cook",
            "property_type": "single_family",
            "instrument_type": "tax_lien",
            "starting_bid": Decimal("6300"),
            "estimated_market_value": Decimal("185000"),
            "other_costs": Decimal("3800"),
            "auction_end": now + timedelta(days=31),
            "confidence": "low",
            "description": "Illustrative lien scenario—not a property sale. Residential owners typically have a statutory redemption period, and a court process is required before any deed.",
        },
        {
            "source": "will_county",
            "external_id": "DEMO-WILL-PIN",
            "title": "Vacant parcel tax-lien scenario",
            "address": "Bolingbrook area parcel preview",
            "city": "Bolingbrook",
            "county": "Will",
            "property_type": "land",
            "instrument_type": "tax_lien",
            "starting_bid": Decimal("2850"),
            "estimated_market_value": Decimal("48000"),
            "other_costs": Decimal("2500"),
            "auction_end": now + timedelta(days=42),
            "confidence": "low",
            "description": "Illustrative annual tax-sale certificate. Confirm parcel usability, municipal liens, zoning, access, and the applicable redemption period.",
        },
        {
            "source": "kane_county",
            "external_id": "DEMO-KANE-PIN",
            "title": "Small residential lien scenario",
            "address": "Aurora area parcel preview",
            "city": "Aurora",
            "county": "Kane",
            "property_type": "single_family",
            "instrument_type": "tax_lien",
            "starting_bid": Decimal("4900"),
            "estimated_market_value": Decimal("214000"),
            "other_costs": Decimal("3300"),
            "auction_end": now + timedelta(days=55),
            "confidence": "low",
            "description": "Illustrative lien investment. The owner can redeem; legal notice deadlines and deed proceedings require specialist review.",
        },
        {
            "source": "lake_county",
            "external_id": "DEMO-LAKE-GREEN",
            "title": "County-owned lot · sealed-bid scenario",
            "address": "North Chicago area parcel preview",
            "city": "North Chicago",
            "county": "Lake",
            "property_type": "land",
            "instrument_type": "county_deed_sale",
            "starting_bid": Decimal("12500"),
            "estimated_market_value": Decimal("56000"),
            "repair_estimate": Decimal("4000"),
            "auction_end": now + timedelta(days=15),
            "confidence": "low",
            "description": "Illustrative county-owned property scenario, distinct from the annual lien sale. Confirm the current green-book list and quitclaim-deed terms.",
        },
        {
            "source": "dupage_county",
            "external_id": "DEMO-DUPAGE-PIN",
            "title": "Commercial tax-lien certificate scenario",
            "address": "Addison area parcel preview",
            "city": "Addison",
            "county": "DuPage",
            "property_type": "commercial",
            "instrument_type": "tax_lien",
            "starting_bid": Decimal("18400"),
            "estimated_market_value": Decimal("420000"),
            "other_costs": Decimal("6500"),
            "auction_end": now + timedelta(days=63),
            "confidence": "low",
            "description": "Illustrative commercial tax-lien scenario. Commercial redemption timelines differ from small residential property.",
        },
    ]

    for sample in samples:
        source = sample["source"]
        listing = Listing(
            **sample,
            source_url=SOURCE_BY_SLUG[source].url,
            status="open",
            is_demo=True,
            how_to_buy=_how_to_buy(sample["instrument_type"]),
            due_diligence=STANDARD_DUE_DILIGENCE,
            raw_data={"demo": True, "notice": "Illustrative data; not an active offering"},
        )
        _score_listing(listing)
        db.add(listing)
    db.commit()


def _how_to_buy(instrument_type: str) -> list[str]:
    if instrument_type == "tax_lien":
        return [
            "Read the county's current registration packet and Illinois Property Tax Code requirements.",
            "Register as a tax buyer and provide the required deposit or collateral by the deadline.",
            "Research the parcel by legal description and PIN; the street address is not controlling.",
            "If successful, pay the county exactly as instructed and calendar all notice/redemption deadlines.",
            "Retain an Illinois tax-sale attorney before pursuing a tax deed.",
        ]
    return [
        "Open the official source listing and download every sale document and addendum.",
        "Register with the official auction or named broker—not through DealSig.",
        "Complete title, occupancy, condition, zoning, and funding diligence.",
        "Send earnest money only to the official escrow/agency channel stated in verified instructions.",
        "Place the bid or offer on the official platform before its deadline.",
    ]
