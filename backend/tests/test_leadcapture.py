"""Lead capture: consent, double opt-in, spam, UTM, tags, unsubscribe (Module 6)."""

from __future__ import annotations

import re

import pytest
from app.models.email import EmailMessage
from app.models.lead import ConsentStatus, Lead
from app.models.user import Role
from sqlmodel import select


async def _login(api, email, password):
    r = await api.post("/api/auth/login", json={"email": email, "password": password})
    assert r.status_code == 200, r.text
    return {"X-CSRF-Token": r.json()["csrf_token"]}


async def _setup_form(api, make_user, *, double_optin=True, consent_required=True,
                      tags=None, form_type="newsletter"):
    h = await _login(api, **await make_user("admin@test.com", "AdminPass123", Role.admin))
    bid = (await api.post("/api/brands", headers=h, json={"name": "Capture Brand"})).json()["id"]
    form = await api.post("/api/forms", headers=h, json={
        "brand_id": bid, "name": "Newsletter", "form_type": form_type,
        "double_optin": double_optin, "consent_required": consent_required,
        "tags_to_apply": tags or [],
    })
    assert form.status_code == 201, form.text
    return h, bid, form.json()["slug"]


async def _confirm_token(async_session_factory):
    async with async_session_factory() as s:
        res = await s.execute(
            select(EmailMessage).where(EmailMessage.category == "double_optin")
        )
        msg = res.scalars().first()
        assert msg is not None, "double opt-in email was not queued"
        return re.search(r"token=([^\"']+)", msg.html_body).group(1)


@pytest.mark.asyncio
async def test_single_optin_confirms_immediately(api, make_user, async_session_factory):
    _h, _bid, slug = await _setup_form(api, make_user, double_optin=False)
    r = await api.post(f"/api/public/forms/{slug}/submit",
                       json={"email": "sub@x.com", "consent": True})
    assert r.status_code == 200
    assert r.json()["requires_confirmation"] is False

    async with async_session_factory() as s:
        lead = (await s.execute(select(Lead).where(Lead.email == "sub@x.com"))).scalar_one()
        assert lead.consent_status == ConsentStatus.confirmed
        welcome = (await s.execute(
            select(EmailMessage).where(EmailMessage.category == "welcome")
        )).scalars().first()
        assert welcome is not None


@pytest.mark.asyncio
async def test_double_optin_then_confirm(api, make_user, async_session_factory):
    _h, _bid, slug = await _setup_form(api, make_user, double_optin=True, tags=["newsletter"])
    submit = await api.post(f"/api/public/forms/{slug}/submit",
                            json={"email": "dbl@x.com", "first_name": "Dee", "consent": True})
    assert submit.status_code == 200
    assert submit.json()["requires_confirmation"] is True

    async with async_session_factory() as s:
        lead = (await s.execute(select(Lead).where(Lead.email == "dbl@x.com"))).scalar_one()
        assert lead.consent_status == ConsentStatus.pending_double_optin

    token = await _confirm_token(async_session_factory)
    confirm = await api.get(f"/api/public/confirm?token={token}")
    assert confirm.status_code == 200
    assert "confirmed" in confirm.text.lower()

    async with async_session_factory() as s:
        lead = (await s.execute(select(Lead).where(Lead.email == "dbl@x.com"))).scalar_one()
        assert lead.consent_status == ConsentStatus.confirmed


@pytest.mark.asyncio
async def test_consent_required_enforced(api, make_user):
    _h, _bid, slug = await _setup_form(api, make_user, consent_required=True)
    r = await api.post(f"/api/public/forms/{slug}/submit", json={"email": "no@x.com"})
    assert r.status_code == 422
    assert r.json()["error"]["code"] == "compliance_blocked"


@pytest.mark.asyncio
async def test_honeypot_blocks_bot_silently(api, make_user, async_session_factory):
    _h, _bid, slug = await _setup_form(api, make_user)
    r = await api.post(f"/api/public/forms/{slug}/submit",
                       json={"email": "bot@x.com", "consent": True, "hp": "i-am-a-bot"})
    assert r.status_code == 200  # bots get a normal-looking response
    async with async_session_factory() as s:
        leads = (await s.execute(select(Lead).where(Lead.email == "bot@x.com"))).scalars().all()
        assert len(leads) == 0  # no lead created


@pytest.mark.asyncio
async def test_invalid_email_rejected(api, make_user):
    _h, _bid, slug = await _setup_form(api, make_user)
    r = await api.post(f"/api/public/forms/{slug}/submit",
                       json={"email": "not-an-email", "consent": True})
    assert r.status_code == 422


@pytest.mark.asyncio
async def test_unsubscribe_then_blocks_resubscribe(api, make_user, async_session_factory):
    from app.services.consent_service import make_unsubscribe_url

    _h, _bid, slug = await _setup_form(api, make_user, double_optin=False)
    await api.post(f"/api/public/forms/{slug}/submit",
                   json={"email": "bye@x.com", "consent": True})
    async with async_session_factory() as s:
        lead = (await s.execute(select(Lead).where(Lead.email == "bye@x.com"))).scalar_one()
        unsub_url = make_unsubscribe_url(lead.id)
    token = re.search(r"token=([^\"'&]+)", unsub_url).group(1)

    out = await api.get(f"/api/public/unsubscribe?token={token}")
    assert out.status_code == 200

    async with async_session_factory() as s:
        lead = (await s.execute(select(Lead).where(Lead.email == "bye@x.com"))).scalar_one()
        assert lead.consent_status == ConsentStatus.unsubscribed

    # Re-subscribe attempt is blocked because the address is now suppressed.
    again = await api.post(f"/api/public/forms/{slug}/submit",
                           json={"email": "bye@x.com", "consent": True})
    assert again.status_code == 422


@pytest.mark.asyncio
async def test_form_post_redirects(api, make_user):
    """A browser form-urlencoded POST (no JS) is handled and confirmed."""
    _h, _bid, slug = await _setup_form(api, make_user, double_optin=False)
    r = await api.post(f"/api/public/forms/{slug}/submit",
                       data={"email": "html@x.com", "consent": "true"})
    assert r.status_code == 200
    assert "thank" in r.text.lower()


@pytest.mark.asyncio
async def test_embeddable_form_is_iframeable(api, make_user):
    _h, _bid, slug = await _setup_form(api, make_user)
    r = await api.get(f"/api/public/forms/{slug}")
    assert r.status_code == 200
    # Embeddable form must allow framing (no DENY) for cross-site embeds.
    assert r.headers.get("x-frame-options") != "DENY"
    assert "frame-ancestors *" in r.headers.get("content-security-policy", "")
    assert "<form" in r.text


@pytest.mark.asyncio
async def test_leads_list_filter_and_export(api, make_user, async_session_factory):
    h, _bid, slug = await _setup_form(api, make_user, double_optin=False)
    await api.post(f"/api/public/forms/{slug}/submit",
                   json={"email": "lead1@x.com", "consent": True})

    listed = await api.get("/api/leads?consent_status=confirmed")
    assert listed.status_code == 200
    assert any(x["email"] == "lead1@x.com" for x in listed.json())

    export = await api.get("/api/leads/export")
    assert export.status_code == 200
    assert "lead1@x.com" in export.text
    assert export.headers["content-type"].startswith("text/csv")
