"""Unit tests for security primitives (Module 3)."""

from __future__ import annotations

import pytest
from app.config import settings
from app.core import sanitize
from app.core.exceptions import AuthError
from app.core.security import (
    WeakPasswordError,
    create_access_token,
    create_refresh_token,
    csrf_tokens_match,
    decode_token,
    generate_csrf_token,
    hash_password,
    make_signed_token,
    read_signed_token,
    validate_password_strength,
    verify_password,
)
from app.core.ssrf import SSRFError, validate_outbound_url


# --- Passwords --------------------------------------------------------------
def test_password_hash_roundtrip():
    h = hash_password("CorrectHorse9")
    assert h != "CorrectHorse9"
    assert verify_password("CorrectHorse9", h)
    assert not verify_password("wrong", h)


def test_password_supports_long_input_no_truncation():
    # bcrypt_sha256 must not silently truncate at 72 bytes.
    a = "A1" + "x" * 100
    b = "A1" + "x" * 100 + "DIFFERENT-TAIL"
    ha = hash_password(a)
    assert verify_password(a, ha)
    assert not verify_password(b, ha)


@pytest.mark.parametrize("bad", ["short1A", "alllowercase123", "ALLUPPER123", "NoDigitsHere"])
def test_weak_passwords_rejected(bad):
    with pytest.raises(WeakPasswordError):
        validate_password_strength(bad)


def test_strong_password_accepted():
    validate_password_strength("StrongPass123")  # no raise


# --- JWT --------------------------------------------------------------------
def test_jwt_roundtrip_and_type_enforced():
    tok = create_access_token("user-123", "owner")
    payload = decode_token(tok, expected_type="access")
    assert payload["sub"] == "user-123"
    assert payload["role"] == "owner"
    # A refresh token must not pass as an access token.
    refresh = create_refresh_token("user-123")
    with pytest.raises(AuthError):
        decode_token(refresh, expected_type="access")


def test_jwt_tampered_rejected():
    tok = create_access_token("u", "viewer")
    with pytest.raises(AuthError):
        decode_token(tok + "x", expected_type="access")


# --- CSRF -------------------------------------------------------------------
def test_csrf_double_submit():
    token = generate_csrf_token()
    assert csrf_tokens_match(token, token)
    assert not csrf_tokens_match(token, "different")
    assert not csrf_tokens_match(None, token)
    assert not csrf_tokens_match(token, None)


# --- Signed links -----------------------------------------------------------
def test_signed_token_roundtrip_and_tamper():
    tok = make_signed_token({"lead": "abc"}, salt="optin")
    assert read_signed_token(tok, salt="optin", max_age_seconds=60)["lead"] == "abc"
    # Wrong salt must fail.
    with pytest.raises(AuthError):
        read_signed_token(tok, salt="other", max_age_seconds=60)


# --- SSRF -------------------------------------------------------------------
def test_ssrf_blocks_empty_allowlist():
    with pytest.raises(SSRFError):
        validate_outbound_url("https://example.com/data")


def test_ssrf_blocks_non_http_scheme(monkeypatch):
    monkeypatch.setattr(settings, "ssrf_allowed_hosts", "example.com")
    with pytest.raises(SSRFError):
        validate_outbound_url("file:///etc/passwd")


def test_ssrf_blocks_private_resolution(monkeypatch):
    # localhost is allowlisted but resolves to loopback -> must be blocked.
    monkeypatch.setattr(settings, "ssrf_allowed_hosts", "localhost")
    with pytest.raises(SSRFError):
        validate_outbound_url("http://localhost/internal")


def test_ssrf_blocks_unlisted_host(monkeypatch):
    monkeypatch.setattr(settings, "ssrf_allowed_hosts", "trusted.com")
    with pytest.raises(SSRFError):
        validate_outbound_url("https://evil.com/x")


# --- HTML sanitization (XSS) ------------------------------------------------
def test_sanitize_strips_script_and_js_href():
    dirty = '<p>ok</p><script>alert(1)</script><a href="javascript:alert(1)">x</a>'
    clean = sanitize.sanitize_html(dirty)
    assert "<script>" not in clean
    assert "javascript:" not in clean
    assert "<p>ok</p>" in clean


def test_strip_all_removes_markup():
    assert sanitize.strip_all("<b>Hi</b> there") == "Hi there"


def test_sanitize_drops_target_attribute():
    # No target=_blank -> reverse-tabnabbing is structurally impossible.
    clean = sanitize.sanitize_html('<a href="https://x.com" target="_blank">x</a>')
    assert "target" not in clean
    assert 'href="https://x.com"' in clean


# --- Production config hard-fail --------------------------------------------
def test_production_config_rejects_insecure_cookies():
    from app.config import Settings
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        # Production with cookie_secure=False must fail closed.
        Settings(app_env="production", secret_key="x" * 40, cookie_secure=False,
                 _env_file=None)


def test_production_config_accepts_secure():
    from app.config import Settings

    s = Settings(app_env="production", secret_key="x" * 40, cookie_secure=True,
                 debug=False, _env_file=None)
    assert s.is_production
