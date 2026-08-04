from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session
from webauthn import (
    base64url_to_bytes,
    generate_authentication_options,
    generate_registration_options,
    options_to_json,
    verify_authentication_response,
    verify_registration_response,
)
from webauthn.helpers.structs import (
    AttestationConveyancePreference,
    AuthenticatorSelectionCriteria,
    PublicKeyCredentialDescriptor,
    ResidentKeyRequirement,
    UserVerificationRequirement,
)

from app.config import get_settings
from app.models import PasskeyCredential, User


def registration_options(db: Session, user: User) -> tuple[str, bytes]:
    settings = get_settings()
    existing = list(
        db.scalars(select(PasskeyCredential).where(PasskeyCredential.user_id == user.id))
    )
    options = generate_registration_options(
        rp_id=settings.passkey_rp_id,
        rp_name="DealSig AI",
        user_id=str(user.id).encode(),
        user_name=user.email,
        user_display_name=user.full_name or user.email,
        attestation=AttestationConveyancePreference.NONE,
        authenticator_selection=AuthenticatorSelectionCriteria(
            resident_key=ResidentKeyRequirement.PREFERRED,
            user_verification=UserVerificationRequirement.REQUIRED,
        ),
        exclude_credentials=[
            PublicKeyCredentialDescriptor(id=base64url_to_bytes(item.credential_id))
            for item in existing
        ],
    )
    return options_to_json(options), options.challenge


def verify_registration(
    db: Session, user: User, credential: dict, expected_challenge: bytes
) -> PasskeyCredential:
    settings = get_settings()
    verification = verify_registration_response(
        credential=credential,
        expected_challenge=expected_challenge,
        expected_rp_id=settings.passkey_rp_id,
        expected_origin=settings.passkey_origin,
        require_user_verification=True,
    )
    credential_id = str(credential["id"])
    if db.scalar(
        select(PasskeyCredential).where(PasskeyCredential.credential_id == credential_id)
    ):
        raise ValueError("This passkey is already registered")
    transports = credential.get("response", {}).get("transports", [])
    item = PasskeyCredential(
        user_id=user.id,
        credential_id=credential_id,
        public_key=verification.credential_public_key,
        sign_count=verification.sign_count,
        transports=[str(value) for value in transports],
        device_type=str(verification.credential_device_type),
        backed_up=verification.credential_backed_up,
    )
    db.add(item)
    db.commit()
    return item


def authentication_options() -> tuple[str, bytes]:
    settings = get_settings()
    options = generate_authentication_options(
        rp_id=settings.passkey_rp_id,
        user_verification=UserVerificationRequirement.REQUIRED,
    )
    return options_to_json(options), options.challenge


def verify_authentication(
    db: Session, credential: dict, expected_challenge: bytes
) -> User:
    settings = get_settings()
    credential_id = str(credential.get("id", ""))
    stored = db.scalar(
        select(PasskeyCredential).where(PasskeyCredential.credential_id == credential_id)
    )
    if not stored:
        raise ValueError("Unknown passkey")
    verification = verify_authentication_response(
        credential=credential,
        expected_challenge=expected_challenge,
        expected_rp_id=settings.passkey_rp_id,
        expected_origin=settings.passkey_origin,
        credential_public_key=stored.public_key,
        credential_current_sign_count=stored.sign_count,
        require_user_verification=True,
    )
    stored.sign_count = verification.new_sign_count
    stored.last_used_at = datetime.now(timezone.utc)
    user = db.get(User, stored.user_id)
    if not user:
        raise ValueError("Passkey owner no longer exists")
    db.commit()
    return user

