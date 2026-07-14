"""Account / membership / signup / invitation schemas (Phase 2 M2)."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, EmailStr, Field


class RegisterRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=1, max_length=200)
    full_name: str = Field(default="", max_length=200)


class AccountOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    type: str
    name: str
    slug: str


class MembershipOut(BaseModel):
    """An account the current user belongs to, with their role in it."""

    account: AccountOut
    role: str
    is_active: bool = False  # is this the request's active account?


class CreateTeamRequest(BaseModel):
    name: str = Field(min_length=1, max_length=200)


class SwitchAccountRequest(BaseModel):
    account_id: uuid.UUID


class MemberOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    user_id: uuid.UUID
    email: str
    full_name: str
    role: str


class UpdateMemberRoleRequest(BaseModel):
    role: str = Field(min_length=1, max_length=20)


# --- Invitations ------------------------------------------------------------

class InviteRequest(BaseModel):
    email: EmailStr
    role: str = Field(default="viewer", min_length=1, max_length=20)


class InvitationOut(BaseModel):
    """Pending invitation (list view — token not included)."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    email: str
    role: str
    created_at: datetime


class InvitationCreatedOut(InvitationOut):
    """Returned only on creation — includes the accept token for link-copy UI."""

    token: str
    accept_url: str


class AcceptInvitationRequest(BaseModel):
    token: str


class ResetMemberPasswordRequest(BaseModel):
    # "link" emails a reset link; "temp" sets a temporary password returned once.
    mode: Literal["link", "temp"] = "link"


class ResetMemberPasswordOut(BaseModel):
    mode: str
    email: str
    emailed: bool = False
    # Present only for mode="temp" — shown once to the admin to relay.
    temporary_password: str | None = None
