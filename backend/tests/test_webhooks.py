"""Resend webhook signature verification + status updates (Module 7)."""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import time
import uuid

import pytest
from app.config import settings
from app.models.brand import Brand
from app.models.email import EmailMessage, EmailStatus
from sqlmodel import select

_SECRET_RAW = base64.b64encode(b"super-secret-webhook-key").decode()
_SECRET = f"whsec_{_SECRET_RAW}"


def _sign(body: bytes, svix_id: str, ts: str) -> str:
    signed = f"{svix_id}.{ts}.".encode() + body
    digest = hmac.new(base64.b64decode(_SECRET_RAW), signed, hashlib.sha256).digest()
    return "v1," + base64.b64encode(digest).decode()


async def _seed_message(async_session_factory, provider_id: str) -> None:
    async with async_session_factory() as s:
        brand = Brand(name="WB", slug=f"wb-{uuid.uuid4().hex[:6]}")
        s.add(brand)
        await s.flush()
        s.add(EmailMessage(
            brand_id=brand.id, to_email="x@y.com", from_email="a@b.com",
            subject="Hi", html_body="<p>Hi</p>", status=EmailStatus.sent,
            provider_message_id=provider_id,
        ))
        await s.commit()


@pytest.mark.asyncio
async def test_valid_signature_updates_status(api, async_session_factory, monkeypatch):
    monkeypatch.setattr(settings, "resend_webhook_secret", _SECRET)
    await _seed_message(async_session_factory, "re_123")

    event = {"type": "email.delivered", "data": {"email_id": "re_123"}}
    body = json.dumps(event).encode()
    svix_id, ts = "msg_1", str(int(time.time()))
    headers = {"svix-id": svix_id, "svix-timestamp": ts,
               "svix-signature": _sign(body, svix_id, ts),
               "content-type": "application/json"}

    resp = await api.post("/api/webhooks/resend", content=body, headers=headers)
    assert resp.status_code == 200
    assert resp.json()["updated"] is True

    async with async_session_factory() as s:
        msg = (await s.execute(
            select(EmailMessage).where(EmailMessage.provider_message_id == "re_123")
        )).scalar_one()
        assert msg.status == EmailStatus.delivered


@pytest.mark.asyncio
async def test_invalid_signature_rejected(api, async_session_factory, monkeypatch):
    monkeypatch.setattr(settings, "resend_webhook_secret", _SECRET)
    await _seed_message(async_session_factory, "re_456")

    body = json.dumps({"type": "email.delivered", "data": {"email_id": "re_456"}}).encode()
    ts = str(int(time.time()))
    headers = {"svix-id": "msg_2", "svix-timestamp": ts,
               "svix-signature": "v1,not-a-valid-signature",
               "content-type": "application/json"}

    resp = await api.post("/api/webhooks/resend", content=body, headers=headers)
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_bounce_adds_suppression(api, async_session_factory, monkeypatch):
    from app.models.email import Suppression

    monkeypatch.setattr(settings, "resend_webhook_secret", _SECRET)
    await _seed_message(async_session_factory, "re_789")

    event = {"type": "email.bounced", "data": {"email_id": "re_789"}}
    body = json.dumps(event).encode()
    svix_id, ts = "msg_3", str(int(time.time()))
    headers = {"svix-id": svix_id, "svix-timestamp": ts,
               "svix-signature": _sign(body, svix_id, ts),
               "content-type": "application/json"}

    resp = await api.post("/api/webhooks/resend", content=body, headers=headers)
    assert resp.status_code == 200
    async with async_session_factory() as s:
        sup = (await s.execute(
            select(Suppression).where(Suppression.email == "x@y.com")
        )).scalar_one_or_none()
        assert sup is not None  # bounce auto-suppresses
