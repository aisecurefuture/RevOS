"""Manual lead add with opt-in attestation (CRM).

An admin can add a lead/contact directly, attesting how the person opted in.
The attestation is captured as an immutable ConsentRecord — the legal basis
for mailing them — and drives the consent lifecycle.
"""

from __future__ import annotations

import re

import pytest
from app.models.crm import Contact
from app.models.email import EmailMessage
from app.models.lead import ConsentRecord, ConsentStatus, Lead
from app.models.user import Role
from sqlmodel import select


async def _login(api, email, password):
    r = await api.post("/api/auth/login", json={"email": email, "password": password})
    assert r.status_code == 200, r.text
    return {"X-CSRF-Token": r.json()["csrf_token"]}


async def _setup(api, make_user):
    h = await _login(api, **await make_user("admin@test.com", "AdminPass123", Role.admin))
    bid = (await api.post("/api/brands", headers=h, json={"name": "CRM Brand"})).json()["id"]
    return h, bid


def _payload(**over):
    base = {
        "email": "lead@x.com",
        "first_name": "Casey",
        "opt_in_attested": True,
        "consent_basis": "Verbal consent at open house 2026-07-20",
        "consent_mode": "express",
    }
    base.update(over)
    return base


@pytest.mark.asyncio
async def test_express_attestation_is_confirmed_and_records_evidence(api, make_user, async_session_factory):
    h, bid = await _setup(api, make_user)
    r = await api.post("/api/leads", headers=h, json=_payload(brand_id=bid))
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["consent_status"] == "confirmed"

    async with async_session_factory() as s:
        lead = (await s.execute(select(Lead).where(Lead.email == "lead@x.com"))).scalar_one()
        assert lead.consent_status == ConsentStatus.confirmed
        assert lead.confirmed_at is not None
        rec = (await s.execute(
            select(ConsentRecord).where(ConsentRecord.lead_id == lead.id)
        )).scalars().all()
        assert len(rec) == 1
        ev = rec[0].evidence
        assert ev["method"] == "manual_attestation"
        assert ev["basis"] == "Verbal consent at open house 2026-07-20"
        assert ev["attested_by_email"] == "admin@test.com"


@pytest.mark.asyncio
async def test_double_optin_attestation_queues_confirmation(api, make_user, async_session_factory):
    h, bid = await _setup(api, make_user)
    r = await api.post("/api/leads", headers=h,
                       json=_payload(brand_id=bid, email="dbl@x.com", consent_mode="double_optin"))
    assert r.status_code == 201, r.text
    assert r.json()["consent_status"] == "pending_double_optin"

    async with async_session_factory() as s:
        msg = (await s.execute(
            select(EmailMessage).where(EmailMessage.category == "double_optin")
        )).scalars().first()
        assert msg is not None, "confirmation email was not queued"
        token = re.search(r"token=([^\"'&]+)", msg.html_body).group(1)

    confirm = await api.get(f"/api/public/confirm?token={token}")
    assert confirm.status_code == 200
    async with async_session_factory() as s:
        lead = (await s.execute(select(Lead).where(Lead.email == "dbl@x.com"))).scalar_one()
        assert lead.consent_status == ConsentStatus.confirmed


@pytest.mark.asyncio
async def test_attestation_is_required(api, make_user):
    h, bid = await _setup(api, make_user)
    r = await api.post("/api/leads", headers=h,
                       json=_payload(brand_id=bid, opt_in_attested=False))
    assert r.status_code == 422
    assert r.json()["error"]["code"] == "compliance_blocked"


@pytest.mark.asyncio
async def test_suppressed_address_cannot_be_manually_added(api, make_user, async_session_factory):
    from app.services.consent_service import make_unsubscribe_url

    h, bid = await _setup(api, make_user)
    # First add + confirm, then unsubscribe to suppress the address.
    await api.post("/api/leads", headers=h, json=_payload(brand_id=bid, email="bye@x.com"))
    async with async_session_factory() as s:
        lead = (await s.execute(select(Lead).where(Lead.email == "bye@x.com"))).scalar_one()
        token = re.search(r"token=([^\"'&]+)", make_unsubscribe_url(lead.id)).group(1)
    assert (await api.get(f"/api/public/unsubscribe?token={token}")).status_code == 200

    again = await api.post("/api/leads", headers=h, json=_payload(brand_id=bid, email="bye@x.com"))
    assert again.status_code == 422
    assert again.json()["error"]["code"] == "compliance_blocked"


@pytest.mark.asyncio
async def test_also_create_contact_links_lead_to_contact(api, make_user, async_session_factory):
    h, bid = await _setup(api, make_user)
    r = await api.post("/api/leads", headers=h, json=_payload(
        brand_id=bid, email="both@x.com", title="VP Sales", also_create_contact=True,
    ))
    assert r.status_code == 201, r.text

    async with async_session_factory() as s:
        lead = (await s.execute(select(Lead).where(Lead.email == "both@x.com"))).scalar_one()
        contact = (await s.execute(select(Contact).where(Contact.email == "both@x.com"))).scalar_one()
        assert lead.contact_id == contact.id
        assert contact.title == "VP Sales"


@pytest.mark.asyncio
async def test_contact_stores_notes_address_and_multi_channels(api, make_user, async_session_factory):
    h, bid = await _setup(api, make_user)
    r = await api.post("/api/leads", headers=h, json=_payload(
        brand_id=bid, email="rich@x.com", phone="555-0001", also_create_contact=True,
        notes="Met at the downtown open house; wants 3BR listings.",
        address_line1="123 Main St", city="Austin", region="TX", postal_code="78701", country="US",
        additional_emails=[{"value": "rich.work@x.com", "label": "work"}],
        additional_phones=[{"value": "555-0002", "label": "office"}],
    ))
    assert r.status_code == 201, r.text

    async with async_session_factory() as s:
        contact = (await s.execute(select(Contact).where(Contact.email == "rich@x.com"))).scalar_one()
        assert contact.notes.startswith("Met at the downtown open house")
        assert contact.city == "Austin" and contact.region == "TX" and contact.postal_code == "78701"
        # Primary is first; extra is stored non-primary.
        assert [e["value"] for e in contact.emails] == ["rich@x.com", "rich.work@x.com"]
        assert contact.emails[0]["is_primary"] is True
        assert contact.emails[1]["is_primary"] is False
        assert [p["value"] for p in contact.phones] == ["555-0001", "555-0002"]
        assert contact.phone == "555-0001"  # scalar mirrors the primary


@pytest.mark.asyncio
async def test_contact_list_out_synthesizes_primary_channel(api, make_user):
    """A contact created through the plain create endpoint (no channel lists)
    still exposes a primary email/phone entry in the API response."""
    h, bid = await _setup(api, make_user)
    created = await api.post("/api/contacts", headers=h, json={
        "brand_id": bid, "email": "plain@x.com", "phone": "555-9999", "first_name": "Plain",
    })
    assert created.status_code == 201, created.text
    listed = await api.get(f"/api/contacts?brand_id={bid}")
    row = next(c for c in listed.json() if c["email"] == "plain@x.com")
    assert row["emails"] == [{"value": "plain@x.com", "label": None, "is_primary": True}]
    assert row["phones"][0]["value"] == "555-9999"


@pytest.mark.asyncio
async def test_update_contact_syncs_primary_and_notes(api, make_user, async_session_factory):
    """Editing the channel lists re-syncs the scalar email/phone primary and
    persists notes/address changes."""
    h, bid = await _setup(api, make_user)
    created = (await api.post("/api/contacts", headers=h, json={
        "brand_id": bid, "email": "old@x.com", "phone": "111",
    })).json()
    cid = created["id"]

    patched = await api.patch(f"/api/contacts/{cid}", headers=h, json={
        "emails": [
            {"value": "new-primary@x.com", "is_primary": True},
            {"value": "secondary@x.com", "label": "work", "is_primary": False},
        ],
        "notes": "Prefers text over email.",
        "city": "Dallas",
    })
    assert patched.status_code == 200, patched.text
    body = patched.json()
    assert body["email"] == "new-primary@x.com"     # scalar re-synced to new primary
    assert body["notes"] == "Prefers text over email."
    assert body["city"] == "Dallas"
    assert [e["value"] for e in body["emails"]] == ["new-primary@x.com", "secondary@x.com"]

    async with async_session_factory() as s:
        contact = (await s.execute(select(Contact).where(Contact.email == "new-primary@x.com"))).scalar_one()
        assert contact.city == "Dallas"


@pytest.mark.asyncio
async def test_delete_contact_soft_deletes(api, make_user):
    h, bid = await _setup(api, make_user)
    cid = (await api.post("/api/contacts", headers=h, json={
        "brand_id": bid, "email": "gone@x.com",
    })).json()["id"]
    assert (await api.delete(f"/api/contacts/{cid}", headers=h)).status_code == 200
    listed = await api.get(f"/api/contacts?brand_id={bid}")
    assert all(c["email"] != "gone@x.com" for c in listed.json())


@pytest.mark.asyncio
async def test_brand_id_defaults_to_first_brand_when_omitted(api, make_user, async_session_factory):
    h, _bid = await _setup(api, make_user)
    r = await api.post("/api/leads", headers=h, json=_payload(email="nobrand@x.com"))
    assert r.status_code == 201, r.text
    async with async_session_factory() as s:
        lead = (await s.execute(select(Lead).where(Lead.email == "nobrand@x.com"))).scalar_one()
        assert lead.brand_id is not None
        assert lead.consent_status == ConsentStatus.confirmed
