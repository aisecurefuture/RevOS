"""Auth request/response schemas."""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr, Field, model_validator


class LoginRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=1, max_length=200)


class PasswordChangeRequest(BaseModel):
    current_password: str = Field(min_length=1, max_length=200)
    new_password: str = Field(min_length=1, max_length=200)


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    email: str
    full_name: str
    role: str
    is_active: bool
    totp_enabled: bool = False
    email_verified: bool = False
    timezone: str | None = None
    avatar_url: str | None = None

    @model_validator(mode="before")
    @classmethod
    def _from_orm(cls, data):
        """Accept ORM objects and compute derived fields."""
        if isinstance(data, dict):
            return data
        settings_dict = getattr(data, "settings", None) or {}
        return {
            "id": data.id,
            "email": data.email,
            "full_name": data.full_name,
            "role": str(data.role),
            "is_active": data.is_active,
            "totp_enabled": getattr(data, "totp_enabled", False),
            "email_verified": getattr(data, "email_verified_at", None) is not None,
            "timezone": settings_dict.get("timezone"),
            "avatar_url": settings_dict.get("avatar_url"),
        }


class LoginResponse(BaseModel):
    user: UserOut
    # Returned so SPA clients can echo it in the X-CSRF-Token header.
    csrf_token: str


# --- 2FA (TOTP) -------------------------------------------------------------
class TwoFASetupResponse(BaseModel):
    secret: str            # shown for manual entry
    otpauth_uri: str       # client renders this as a QR code


class TwoFACodeRequest(BaseModel):
    code: str = Field(min_length=1, max_length=40)


class RecoveryCodesResponse(BaseModel):
    recovery_codes: list[str]   # shown ONCE


class TwoFADisableRequest(BaseModel):
    password: str = Field(min_length=1, max_length=200)
    code: str = Field(min_length=1, max_length=40)


class TwoFALoginRequest(BaseModel):
    pending_token: str
    code: str = Field(min_length=1, max_length=40)


# --- Profile ----------------------------------------------------------------
class UpdateProfileRequest(BaseModel):
    full_name: str | None = Field(default=None, max_length=200)
    timezone: str | None = Field(default=None, max_length=80)
    avatar_url: str | None = Field(default=None, max_length=500)
    notifications: dict | None = None
