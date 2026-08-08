import re
import time

import pytest

from app.security import rate_limiter
from app.services import contact
from app.services.contact import ContactSubmission


@pytest.fixture(autouse=True)
def reset_rate_limiter():
    """The limiter is a process-wide singleton; 5 posts/15min would leak across tests."""
    rate_limiter._hits.clear()
    yield
    rate_limiter._hits.clear()


@pytest.fixture
def enabled_form(monkeypatch):
    """Point the cached settings at a configured mailbox and capture the send."""
    from app import main
    from app.config import get_settings

    settings = get_settings()
    monkeypatch.setattr(settings, "resend_api_key", "re_test", raising=False)
    monkeypatch.setattr(settings, "resend_from_email", "DealSig <access@dealsig.ai>", raising=False)
    monkeypatch.setattr(settings, "contact_recipients", "ops@dealsig.ai,founders@dealsig.ai")
    monkeypatch.setattr(settings, "resend_reply_to", "support@dealsig.ai")
    assert main.settings.contact_form_enabled

    sent: list[dict] = []

    async def fake_send(**kwargs):
        sent.append(kwargs)

    monkeypatch.setattr(contact, "send_via_resend", fake_send)
    return sent


@pytest.fixture
def easy_challenge(monkeypatch):
    """Drop proof-of-work difficulty so tests stay fast; the logic is unchanged."""
    from app.config import get_settings

    monkeypatch.setattr(get_settings(), "contact_pow_bits", 8)
    return 8


def form_fields(client, path="/contact", *, age_seconds=10, bits=8) -> dict:
    """GET the form and return the hidden fields a real browser would submit."""
    from app.services import challenge

    page = client.get(path)
    csrf = re.search(r'name="csrf_token" value="([^"]+)"', page.text)
    assert csrf, "no CSRF token rendered"
    # Re-issue the challenge backdated past MIN_SECONDS instead of sleeping.
    token = challenge.issue(csrf.group(1), now=int(time.time()) - age_seconds)
    nonce = token.split(".")[1]
    counter = 0
    while not challenge.solution_is_valid(nonce, str(counter), bits):
        counter += 1
    return {
        "csrf_token": csrf.group(1),
        "challenge_token": token,
        "challenge_counter": str(counter),
        "not_a_robot": "1",
    }


def csrf_token(client, path="/contact") -> str:
    page = client.get(path)
    match = re.search(r'name="csrf_token" value="([^"]+)"', page.text)
    assert match, "no CSRF token rendered"
    return match.group(1)


def _submission(**overrides) -> ContactSubmission:
    values = {
        "email": "buyer@example.com",
        "message": "Please add the Cook County scavenger sale calendar.",
        "topic": "data_source",
        "name": "Pat Kelly",
        "subject": "Scavenger sale",
    }
    values.update(overrides)
    return ContactSubmission(**values)


def test_subject_uses_topic_label_and_stays_single_line():
    submission = _submission(subject="Line one\nBcc: attacker@example.com")
    subject = contact.build_subject(submission)
    assert "\n" not in subject
    assert "data source suggestion" in subject.lower()


def test_subject_falls_back_to_sender_when_blank():
    assert "buyer@example.com" in contact.build_subject(_submission(subject=""))


def test_html_body_escapes_submitted_content():
    submission = _submission(message="<script>alert(1)</script>", name="<b>Pat</b>")
    body = contact.build_html(submission)
    assert "<script>" not in body
    assert "&lt;script&gt;" in body
    assert "&lt;b&gt;Pat&lt;/b&gt;" in body


def test_text_body_carries_reply_address_and_message():
    text = contact.build_text(_submission())
    assert "buyer@example.com" in text
    assert "Cook County scavenger sale" in text


def test_send_requires_configured_recipients(monkeypatch):
    import pytest

    from app.config import Settings

    settings = Settings(session_secret="x" * 32, resend_api_key="re_test", contact_recipients="")
    monkeypatch.setattr(contact, "get_settings", lambda: settings)
    with pytest.raises(contact.ContactNotConfigured):
        import asyncio

        asyncio.run(contact.send_contact_message(_submission()))


def test_recipient_and_reply_to_lists_parse_commas():
    from app.config import Settings

    settings = Settings(
        session_secret="x" * 32,
        contact_recipients=" ops@dealsig.ai , founders@dealsig.ai ,",
        resend_reply_to="support@dealsig.ai",
        resend_api_key="re_test",
    )
    assert settings.contact_recipient_list == ["ops@dealsig.ai", "founders@dealsig.ai"]
    assert settings.reply_to_list == ["support@dealsig.ai"]
    assert settings.contact_form_enabled is True


def test_contact_form_disabled_without_recipients():
    from app.config import Settings

    settings = Settings(session_secret="x" * 32, resend_api_key="re_test", contact_recipients="")
    assert settings.contact_form_enabled is False


# --- route behaviour --------------------------------------------------------


def test_contact_page_renders_publicly(client):
    response = client.get("/contact")
    assert response.status_code == 200
    assert "Tell us what you need" in response.text


def test_page_renders_the_hooks_the_browser_solver_depends_on(client):
    """app.js reads these exact attributes; renaming one silently breaks the box."""
    page = client.get("/contact").text
    for hook in (
        "data-robot-check",
        "data-pow-bits=",
        "data-pow-counter",
        "data-robot-toggle",
        "data-robot-status",
        "data-contact-submit",
        'name="challenge_token"',
        'name="not_a_robot"',
    ):
        assert hook in page, f"missing {hook}"
    # Submit ships disabled: it is the checkbox handler that enables it.
    assert re.search(r"data-contact-submit[^>]*disabled", page)
    # Challenge must be a well-formed issued_at.nonce.signature triple.
    token = re.search(r'name="challenge_token" value="([^"]+)"', page)
    assert token and len(token.group(1).split(".")) == 3


def test_post_without_csrf_is_rejected(client):
    response = client.post(
        "/contact",
        data={"email": "buyer@example.com", "message": "A long enough message here."},
    )
    assert response.status_code == 403


def test_disabled_form_reports_unavailable_instead_of_sending(client):
    response = client.post(
        "/contact",
        data={
            "csrf_token": csrf_token(client),
            "email": "buyer@example.com",
            "message": "A long enough message here.",
        },
    )
    assert response.status_code == 503
    assert "not configured" in response.text


def test_honeypot_drops_submission_but_reports_success(client, enabled_form):
    response = client.post(
        "/contact",
        data={
            "csrf_token": csrf_token(client),
            "email": "bot@example.com",
            "message": "Buy cheap things at my website right now.",
            "company": "SpamCo",
        },
        follow_redirects=False,
    )
    assert response.status_code == 303
    assert response.headers["location"] == "/contact?sent=1"
    assert enabled_form == [], "honeypot submission must not send mail"


def test_invalid_email_is_rejected(client, enabled_form, easy_challenge):
    response = client.post(
        "/contact",
        data={
            **form_fields(client),
            "email": "not-an-email",
            "message": "A long enough message here.",
        },
    )
    assert response.status_code == 400
    assert enabled_form == []


def test_too_short_message_is_rejected(client, enabled_form, easy_challenge):
    response = client.post(
        "/contact",
        data={**form_fields(client), "email": "buyer@example.com", "message": "hi"},
    )
    assert response.status_code == 400
    assert enabled_form == []


def test_unticked_box_blocks_the_send(client, enabled_form, easy_challenge):
    data = form_fields(client)
    data.pop("not_a_robot")
    response = client.post(
        "/contact",
        data={**data, "email": "bot@example.com", "message": "A long enough message here."},
    )
    assert response.status_code == 400
    assert "verification box" in response.text
    assert enabled_form == []


def test_forged_challenge_blocks_the_send(client, enabled_form, easy_challenge):
    response = client.post(
        "/contact",
        data={
            **form_fields(client),
            "challenge_token": f"{int(time.time()) - 10}.deadbeef.{'0' * 32}",
            "email": "bot@example.com",
            "message": "A long enough message here.",
        },
    )
    assert response.status_code == 400
    assert enabled_form == [], "a forged challenge must never reach Resend"


def test_unsolved_challenge_blocks_the_send(client, enabled_form, easy_challenge):
    response = client.post(
        "/contact",
        data={
            **form_fields(client),
            "challenge_counter": "",
            "email": "bot@example.com",
            "message": "A long enough message here.",
        },
    )
    assert response.status_code == 400
    assert enabled_form == []


def test_instant_submission_blocks_the_send(client, enabled_form, easy_challenge):
    """A form filled and posted in under MIN_SECONDS did not have a human on it."""
    response = client.post(
        "/contact",
        data={
            **form_fields(client, age_seconds=0),
            "email": "bot@example.com",
            "message": "A long enough message here.",
        },
    )
    assert response.status_code == 400
    assert enabled_form == []


def test_optional_daily_cap_refuses_once_spent(client, enabled_form, easy_challenge, monkeypatch):
    from app.config import get_settings
    from app.services import contact as contact_service

    monkeypatch.setattr(get_settings(), "contact_daily_limit", 1)
    monkeypatch.setattr(contact_service, "delivered_today", lambda db: 1)
    response = client.post(
        "/contact",
        data={
            **form_fields(client),
            "email": "buyer@example.com",
            "message": "A long enough message here.",
        },
    )
    assert response.status_code == 429
    assert enabled_form == []


def test_no_cap_by_default(client, enabled_form, easy_challenge):
    from app.config import get_settings
    from app.services import contact as contact_service

    assert get_settings().contact_daily_limit == 0
    from app.database import SessionLocal

    with SessionLocal() as db:
        assert contact_service.daily_budget_remaining(db) is None


def test_valid_submission_sends_to_configured_recipients(client, enabled_form, easy_challenge):
    response = client.post(
        "/contact",
        data={
            **form_fields(client),
            "email": "buyer@example.com",
            "name": "Pat",
            "topic": "feature_request",
            "subject": "Saved search alerts",
            "message": "Please email me when a new Cook County listing is scored.",
        },
        follow_redirects=False,
    )
    assert response.status_code == 303
    assert response.headers["location"] == "/contact?sent=1"
    assert len(enabled_form) == 1
    call = enabled_form[0]
    # Recipients come from config only — never from the submitter.
    assert call["to"] == ["ops@dealsig.ai", "founders@dealsig.ai"]
    # Submitter first so Reply reaches them, configured Reply-To appended.
    assert call["reply_to"] == ["buyer@example.com"]
    assert "Saved search alerts" in call["subject"]
    assert "Cook County listing" in call["text"]


def test_rejected_submission_reflects_input_escaped(client, enabled_form, easy_challenge):
    """A rejected post re-renders what was typed; it must come back escaped."""
    payload = '"><script>alert(1)</script>'
    response = client.post(
        "/contact",
        data={
            **form_fields(client),
            "email": "not-an-email",
            "subject": payload,
            "message": payload + " and more text to pass the length check",
        },
    )
    assert response.status_code == 400
    assert "<script>alert(1)</script>" not in response.text
    assert "&lt;script&gt;" in response.text


def test_rate_limit_caps_repeated_submissions(client, enabled_form):
    token = csrf_token(client)
    payload = {
        "csrf_token": token,
        "email": "buyer@example.com",
        "message": "A perfectly reasonable message goes here.",
    }
    statuses = [
        client.post("/contact", data=payload, follow_redirects=False).status_code
        for _ in range(7)
    ]
    assert 429 in statuses, f"expected the limiter to kick in, got {statuses}"
