"""Core security primitives: password hashing, JWT, CSRF, signed links.

- Passwords use ``bcrypt_sha256`` (bcrypt with a SHA-256 pre-hash) so arbitrary
  length passwords are supported without bcrypt's silent 72-byte truncation.
- Access/refresh tokens are JWTs (HS256) carrying a typed claim so a refresh
  token can never be used as an access token.
- CSRF uses a signed double-submit token (cookie value must equal the
  ``X-CSRF-Token`` header), compared in constant time.
- Signed, time-limited tokens back double opt-in / unsubscribe links (Module 6).
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import uuid
from datetime import timedelta

import bcrypt
import jwt
from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer

from app.config import settings
from app.core.exceptions import AuthError, RevOSError
from app.models.base import utcnow

# Cookie names (centralized so router + middleware agree).
ACCESS_COOKIE = "revos_access"
REFRESH_COOKIE = "revos_refresh"
CSRF_COOKIE = "revos_csrf"
CSRF_HEADER = "X-CSRF-Token"


# --- Passwords --------------------------------------------------------------
class WeakPasswordError(RevOSError):
    code = "weak_password"
    status_code = 422


def validate_password_strength(password: str) -> None:
    """Enforce the configured password policy. Raises WeakPasswordError."""
    if len(password) < settings.password_min_length:
        raise WeakPasswordError(
            f"Password must be at least {settings.password_min_length} characters."
        )
    if len(password) > settings.password_max_length:
        raise WeakPasswordError(
            f"Password must be at most {settings.password_max_length} characters."
        )
    if password.lower() == password or password.upper() == password:
        raise WeakPasswordError("Password must mix upper and lower case letters.")
    if not any(c.isdigit() for c in password):
        raise WeakPasswordError("Password must contain at least one digit.")


def _prehash(password: str) -> bytes:
    """SHA-256 + base64 pre-hash so any-length passwords fit bcrypt's 72-byte
    input without silent truncation (base64 output is 44 bytes, NUL-free)."""
    digest = hashlib.sha256(password.encode("utf-8")).digest()
    return base64.b64encode(digest)


def hash_password(password: str) -> str:
    return bcrypt.hashpw(_prehash(password), bcrypt.gensalt()).decode("utf-8")


def verify_password(password: str, hashed: str) -> bool:
    try:
        return bcrypt.checkpw(_prehash(password), hashed.encode("utf-8"))
    except (ValueError, TypeError):
        return False


# --- JWT --------------------------------------------------------------------
def _create_token(subject: str, token_type: str, expires: timedelta, **claims) -> str:
    now = utcnow()
    payload = {
        "sub": subject,
        "type": token_type,
        "iat": now,
        "nbf": now,
        "exp": now + expires,
        "jti": uuid.uuid4().hex,
        **claims,
    }
    return jwt.encode(payload, settings.secret_key, algorithm=settings.jwt_algorithm)


def create_access_token(
    subject: str, role: str, token_version: int = 0, active_account: str | None = None
) -> str:
    claims = {"role": role, "tv": token_version}
    if active_account is not None:
        claims["act"] = active_account  # active account (tenant) id
    return _create_token(
        subject,
        "access",
        timedelta(minutes=settings.access_token_expire_minutes),
        **claims,
    )


def create_refresh_token(subject: str, token_version: int = 0) -> str:
    return _create_token(
        subject,
        "refresh",
        timedelta(days=settings.refresh_token_expire_days),
        tv=token_version,
    )


def decode_token(token: str, *, expected_type: str | None = None) -> dict:
    """Decode and validate a JWT. Raises AuthError on any problem."""
    try:
        payload = jwt.decode(
            token,
            settings.secret_key,
            algorithms=[settings.jwt_algorithm],
            options={"require": ["exp", "sub", "type"]},
        )
    except jwt.ExpiredSignatureError as exc:
        raise AuthError("Token has expired.") from exc
    except jwt.InvalidTokenError as exc:
        raise AuthError("Invalid authentication token.") from exc
    if expected_type and payload.get("type") != expected_type:
        raise AuthError("Wrong token type.")
    return payload


# --- CSRF (signed double-submit) -------------------------------------------
def _csrf_serializer() -> URLSafeTimedSerializer:
    return URLSafeTimedSerializer(settings.secret_key, salt="revos-csrf")


def generate_csrf_token() -> str:
    return _csrf_serializer().dumps(uuid.uuid4().hex)


def csrf_tokens_match(cookie_token: str | None, header_token: str | None) -> bool:
    """Constant-time double-submit check; both must be present, valid, equal."""
    if not cookie_token or not header_token:
        return False
    if not hmac.compare_digest(cookie_token, header_token):
        return False
    try:
        # Confirm the token is one we signed and is not absurdly old (8h).
        _csrf_serializer().loads(cookie_token, max_age=60 * 60 * 8)
    except (BadSignature, SignatureExpired):
        return False
    return True


# --- Signed, time-limited tokens (opt-in / unsubscribe links) ---------------
def make_signed_token(data: dict, *, salt: str) -> str:
    return URLSafeTimedSerializer(settings.secret_key, salt=salt).dumps(data)


def read_signed_token(token: str, *, salt: str, max_age_seconds: int) -> dict:
    """Read a signed token. Raises AuthError if tampered or expired."""
    try:
        return URLSafeTimedSerializer(settings.secret_key, salt=salt).loads(
            token, max_age=max_age_seconds
        )
    except SignatureExpired as exc:
        raise AuthError("This link has expired.") from exc
    except BadSignature as exc:
        raise AuthError("This link is invalid.") from exc
