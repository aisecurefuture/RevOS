"""Email service: provider, send-time compliance enforcement (Module 7)."""

from __future__ import annotations

import uuid

import pytest
from app.models.brand import Brand
from app.models.email import EmailCategory, EmailMessage, EmailStatus, Suppression
from app.models.lead import ConsentStatus, Lead
from app.services import email_service
from app.services.email_service import ResendProvider, build_payload


async def _brand(session) -> Brand:
    brand = Brand(name="B", slug=f"b-{uuid.uuid4().hex[:6]}")
    session.add(brand)
    await session.flush()
    return brand


def _msg(brand_id, **kw) -> EmailMessage:
    defaults = {
        "brand_id": brand_id, "to_email": "x@y.com", "from_email": "from@b.com",
        "subject": "Hi", "html_body": "<p>Hi</p>",
        "category": EmailCategory.transactional, "status": EmailStatus.draft,
    }
    defaults.update(kw)
    return EmailMessage(**defaults)


@pytest.mark.asyncio
async def test_send_in_test_mode_records_not_delivers(async_session_factory):
    async with async_session_factory() as s:
        brand = await _brand(s)
        msg = _msg(brand.id)
        s.add(msg)
        await s.flush()
        out = await email_service.send_message(s, msg)
        assert out.status == EmailStatus.sent
        assert out.test_mode is True
        assert out.provider_message_id.startswith("test_")


@pytest.mark.asyncio
async def test_suppressed_address_is_never_sent(async_session_factory):
    async with async_session_factory() as s:
        brand = await _brand(s)
        s.add(Suppression(brand_id=brand.id, email="sup@y.com"))
        msg = _msg(brand.id, to_email="sup@y.com", category=EmailCategory.campaign)
        s.add(msg)
        await s.flush()
        out = await email_service.send_message(s, msg)
        assert out.status == EmailStatus.suppressed
        assert out.error == "suppressed"


@pytest.mark.asyncio
async def test_campaign_to_unconfirmed_lead_blocked(async_session_factory):
    async with async_session_factory() as s:
        brand = await _brand(s)
        lead = Lead(brand_id=brand.id, email="lead@y.com",
                    consent_status=ConsentStatus.none)
        s.add(lead)
        await s.flush()
        msg = _msg(brand.id, to_email="lead@y.com",
                   category=EmailCategory.campaign, lead_id=lead.id)
        s.add(msg)
        await s.flush()
        out = await email_service.send_message(s, msg)
        assert out.status == EmailStatus.suppressed
        assert out.error == "unconfirmed_consent"


def test_resend_provider_builds_payload(monkeypatch):
    import resend

    captured: dict = {}

    class FakeEmails:
        @staticmethod
        def send(payload):
            captured.update(payload)
            return {"id": "re_abc123"}

    monkeypatch.setattr(resend, "Emails", FakeEmails)
    provider = ResendProvider("re_test_key")

    msg = _msg(uuid.uuid4(), from_name="CyberArmor", category=EmailCategory.campaign)
    payload = build_payload(msg, unsubscribe_url="https://app/unsub?token=t")
    result = provider.send(payload)

    assert result.id == "re_abc123"
    assert captured["from"] == "CyberArmor <from@b.com>"
    assert captured["to"] == ["x@y.com"]
    # Marketing email must carry a one-click unsubscribe header.
    assert "List-Unsubscribe" in captured["headers"]
