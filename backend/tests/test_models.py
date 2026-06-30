"""Model-layer tests (Module 2): consent rules, enum storage, constraints."""

from __future__ import annotations

import pytest
from app.models import (
    Brand,
    BrandType,
    ConsentStatus,
    Lead,
    Offer,
    OfferType,
    Suppression,
)
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError


def _brand(db_session, slug="cyberarmor"):
    b = Brand(name="CyberArmor", slug=slug, brand_type=BrandType.company)
    db_session.add(b)
    db_session.commit()
    db_session.refresh(b)
    return b


def test_lead_consent_gates_mailability(db_session):
    brand = _brand(db_session)
    lead = Lead(brand_id=brand.id, email="ciso@example.com")
    db_session.add(lead)
    db_session.commit()
    db_session.refresh(lead)

    # Imported / unknown consent → NOT mailable (CAN-SPAM/GDPR safe default).
    assert lead.consent_status == ConsentStatus.none
    assert lead.is_mailable is False

    lead.consent_status = ConsentStatus.confirmed
    db_session.add(lead)
    db_session.commit()
    assert lead.is_mailable is True

    # Soft-deleted leads are never mailable even if confirmed.
    from app.models.base import utcnow

    lead.deleted_at = utcnow()
    assert lead.is_mailable is False


def test_enum_stored_as_plain_string(db_session):
    _brand(db_session)
    # Raw SQL confirms we store "company", not "BrandType.company".
    value = db_session.execute(text("SELECT brand_type FROM brands LIMIT 1")).scalar_one()
    assert value == "company"


def test_unique_lead_email_per_brand(db_session):
    brand = _brand(db_session)
    db_session.add(Lead(brand_id=brand.id, email="dup@example.com"))
    db_session.commit()
    db_session.add(Lead(brand_id=brand.id, email="dup@example.com"))
    with pytest.raises(IntegrityError):
        db_session.commit()


def test_offer_unique_slug_per_brand(db_session):
    brand = _brand(db_session)
    db_session.add(Offer(brand_id=brand.id, name="Checklist", slug="checklist",
                         offer_type=OfferType.lead_magnet))
    db_session.commit()
    db_session.add(Offer(brand_id=brand.id, name="Checklist 2", slug="checklist",
                         offer_type=OfferType.lead_magnet))
    with pytest.raises(IntegrityError):
        db_session.commit()


def test_suppression_global_and_branded(db_session):
    brand = _brand(db_session)
    # Global suppression (brand_id NULL) and a branded one can coexist.
    db_session.add(Suppression(email="bounce@example.com"))
    db_session.add(Suppression(brand_id=brand.id, email="bounce@example.com"))
    db_session.commit()
    count = db_session.execute(
        text("SELECT count(*) FROM suppressions WHERE email = :e"),
        {"e": "bounce@example.com"},
    ).scalar_one()
    assert count == 2
