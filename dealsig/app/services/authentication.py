from __future__ import annotations

import hashlib
import hmac
import secrets
from datetime import datetime, timedelta, timezone

import httpx
from authlib.integrations.starlette_client import OAuth
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.config import get_settings
from app.models import AuthIdentity, EmailLoginCode, User

settings = get_settings()
oauth = OAuth()


def _register_oidc_providers() -> None:
    if settings.google_client_id and settings.google_client_secret:
        oauth.register(
            name="google",
            client_id=settings.google_client_id,
            client_secret=settings.google_client_secret,
            server_metadata_url="https://accounts.google.com/.well-known/openid-configuration",
            client_kwargs={"scope": "openid email profile", "code_challenge_method": "S256"},
        )
    if settings.microsoft_client_id and settings.microsoft_client_secret:
        oauth.register(
            name="microsoft",
            client_id=settings.microsoft_client_id,
            client_secret=settings.microsoft_client_secret,
            server_metadata_url=(
                "https://login.microsoftonline.com/common/v2.0/.well-known/openid-configuration"
            ),
            client_kwargs={"scope": "openid email profile", "code_challenge_method": "S256"},
        )
    if settings.apple_client_id and settings.apple_client_secret:
        oauth.register(
            name="apple",
            client_id=settings.apple_client_id,
            client_secret=settings.apple_client_secret,
            server_metadata_url="https://appleid.apple.com/.well-known/openid-configuration",
            client_kwargs={"scope": "openid email name", "code_challenge_method": "S256"},
        )


_register_oidc_providers()


def configured_sso() -> dict[str, bool]:
    return {
        "google": bool(settings.google_client_id and settings.google_client_secret),
        "microsoft": bool(settings.microsoft_client_id and settings.microsoft_client_secret),
        "apple": bool(settings.apple_client_id and settings.apple_client_secret),
    }


def code_digest(email: str, code: str) -> str:
    message = f"{email.lower()}:{code}".encode()
    return hmac.new(settings.session_secret.encode(), message, hashlib.sha256).hexdigest()


def create_email_code(db: Session, email: str, requested_ip: str) -> str:
    normalized = email.strip().lower()
    now = datetime.now(timezone.utc)
    db.execute(
        update(EmailLoginCode)
        .where(EmailLoginCode.email == normalized, EmailLoginCode.consumed_at.is_(None))
        .values(consumed_at=now)
    )
    code = f"{secrets.randbelow(1_000_000):06d}"
    db.add(
        EmailLoginCode(
            email=normalized,
            code_hash=code_digest(normalized, code),
            expires_at=now + timedelta(minutes=settings.auth_code_ttl_minutes),
            requested_ip=requested_ip[:80],
        )
    )
    db.commit()
    return code


def verify_email_code(db: Session, email: str, code: str) -> User | None:
    normalized = email.strip().lower()
    login_code = db.scalar(
        select(EmailLoginCode)
        .where(EmailLoginCode.email == normalized, EmailLoginCode.consumed_at.is_(None))
        .order_by(EmailLoginCode.created_at.desc())
        .limit(1)
    )
    if not login_code:
        return None
    expires_at = login_code.expires_at
    if not expires_at.tzinfo:
        expires_at = expires_at.replace(tzinfo=timezone.utc)
    now = datetime.now(timezone.utc)
    if expires_at < now or login_code.attempts >= 5:
        login_code.consumed_at = now
        db.commit()
        return None
    login_code.attempts += 1
    if not hmac.compare_digest(login_code.code_hash, code_digest(normalized, code.strip())):
        db.commit()
        return None
    login_code.consumed_at = now
    user = db.scalar(select(User).where(User.email == normalized))
    if not user:
        user = User(email=normalized, full_name=normalized.split("@", 1)[0])
        db.add(user)
    user.email_verified_at = now
    db.commit()
    return user


async def send_email_code(email: str, code: str) -> None:
    if settings.demo_mode and not settings.resend_api_key:
        return
    if not settings.resend_api_key or not settings.resend_from_email:
        raise RuntimeError("Resend email delivery is not configured")
    async with httpx.AsyncClient(timeout=10, follow_redirects=False) as client:
        response = await client.post(
            "https://api.resend.com/emails",
            headers={
                "Authorization": f"Bearer {settings.resend_api_key}",
                "Content-Type": "application/json",
                "User-Agent": "DealSigAI/0.1",
                "Idempotency-Key": f"login-{code_digest(email, code)[:40]}",
            },
            json={
                "from": settings.resend_from_email,
                "to": [email],
                "subject": f"{code} is your DealSig sign-in code",
                "text": (
                    f"Your DealSig AI sign-in code is {code}.\n\n"
                    f"It expires in {settings.auth_code_ttl_minutes} minutes and can be used once.\n"
                    "If you did not request this code, you can ignore this email."
                ),
                "html": (
                    "<div style='font-family:Arial,sans-serif;max-width:520px;padding:24px'>"
                    "<p style='color:#60706a;font-size:13px'>DEALSIG AI · SECURE ACCESS</p>"
                    "<h1 style='color:#10201c;font-size:26px'>Your sign-in code</h1>"
                    f"<p style='font-size:36px;letter-spacing:8px;font-weight:700'>{code}</p>"
                    f"<p style='color:#60706a'>Expires in {settings.auth_code_ttl_minutes} minutes "
                    "and can be used once.</p><p style='color:#87948f;font-size:12px'>"
                    "If you did not request this code, you can ignore this email.</p></div>"
                ),
                "tags": [{"name": "category", "value": "login_code"}],
            },
        )
    response.raise_for_status()


def resolve_sso_user(db: Session, provider: str, claims: dict) -> User:
    subject = str(claims.get("sub", ""))
    email = str(claims.get("email") or claims.get("preferred_username") or "").lower()
    if not subject or not email or "@" not in email:
        raise ValueError("The identity provider did not return a usable email and subject")
    identity = db.scalar(
        select(AuthIdentity).where(
            AuthIdentity.provider == provider, AuthIdentity.subject == subject
        )
    )
    if identity:
        user = db.get(User, identity.user_id)
        if not user:
            raise ValueError("Linked account no longer exists")
        return user
    existing = db.scalar(select(User).where(User.email == email))
    if existing:
        raise ValueError(
            "An account already uses this email. Sign in by email code, then link SSO from Security."
        )
    user = User(
        email=email,
        full_name=str(claims.get("name") or email.split("@", 1)[0])[:160],
        email_verified_at=datetime.now(timezone.utc),
    )
    db.add(user)
    db.flush()
    db.add(
        AuthIdentity(
            user_id=user.id,
            provider=provider,
            subject=subject,
            email_at_link=email,
        )
    )
    db.commit()
    return user
