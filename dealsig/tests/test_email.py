import asyncio

import pytest

from app.config import Settings
from app.services import email as email_service


class _Response:
    status_code = 200

    def raise_for_status(self):
        return None


class _CapturingClient:
    """Stands in for httpx.AsyncClient and records the outgoing Resend call."""

    calls: list[dict] = []

    def __init__(self, *args, **kwargs):
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return False

    async def post(self, url, headers=None, json=None):
        type(self).calls.append({"url": url, "headers": headers, "json": json})
        return _Response()


@pytest.fixture
def capture(monkeypatch):
    _CapturingClient.calls = []
    monkeypatch.setattr(email_service.httpx, "AsyncClient", _CapturingClient)
    return _CapturingClient.calls


def _configure(monkeypatch, **overrides):
    values = {
        "session_secret": "x" * 32,
        "resend_api_key": "re_test_key",
        "resend_from_email": "DealSig AI <access@dealsig.ai>",
    }
    values.update(overrides)
    settings = Settings(**values)
    monkeypatch.setattr(email_service, "get_settings", lambda: settings)
    return settings


def test_configured_reply_to_is_appended_after_the_caller_address(monkeypatch, capture):
    _configure(monkeypatch, resend_reply_to="support@dealsig.ai, ops@dealsig.ai")
    asyncio.run(
        email_service.send_via_resend(
            to=["ops@dealsig.ai"],
            subject="Test",
            text="body",
            reply_to=["submitter@example.com"],
        )
    )
    payload = capture[0]["json"]
    assert payload["reply_to"] == [
        "submitter@example.com",
        "support@dealsig.ai",
        "ops@dealsig.ai",
    ]


def test_reply_to_is_omitted_when_nothing_is_configured(monkeypatch, capture):
    _configure(monkeypatch, resend_reply_to="")
    asyncio.run(email_service.send_via_resend(to=["ops@dealsig.ai"], subject="T", text="b"))
    assert "reply_to" not in capture[0]["json"]


def test_duplicate_reply_to_addresses_collapse(monkeypatch, capture):
    _configure(monkeypatch, resend_reply_to="same@dealsig.ai")
    asyncio.run(
        email_service.send_via_resend(
            to=["ops@dealsig.ai"], subject="T", text="b", reply_to=["same@dealsig.ai"]
        )
    )
    assert capture[0]["json"]["reply_to"] == ["same@dealsig.ai"]


def test_from_address_always_comes_from_config(monkeypatch, capture):
    _configure(monkeypatch)
    asyncio.run(
        email_service.send_via_resend(
            to=["ops@dealsig.ai"], subject="T", text="b", reply_to=["stranger@example.com"]
        )
    )
    assert capture[0]["json"]["from"] == "DealSig AI <access@dealsig.ai>"


def test_api_key_goes_in_the_header_not_the_body(monkeypatch, capture):
    _configure(monkeypatch)
    asyncio.run(email_service.send_via_resend(to=["ops@dealsig.ai"], subject="T", text="b"))
    call = capture[0]
    assert call["headers"]["Authorization"] == "Bearer re_test_key"
    assert "re_test_key" not in str(call["json"])


def test_missing_credentials_raise_before_any_request(monkeypatch, capture):
    _configure(monkeypatch, resend_api_key="")
    with pytest.raises(email_service.EmailNotConfigured):
        asyncio.run(email_service.send_via_resend(to=["ops@dealsig.ai"], subject="T", text="b"))
    assert capture == []


def test_empty_recipient_list_raises_before_any_request(monkeypatch, capture):
    _configure(monkeypatch)
    with pytest.raises(email_service.EmailNotConfigured):
        asyncio.run(email_service.send_via_resend(to=[], subject="T", text="b"))
    assert capture == []
