"""Avatar persona identity — the creator's digital-twin likeness (Phase 3 M2).

A ``PersonaIdentity`` is the consented, editable record that grounds the
self-hosted avatar+voice pipeline (M3+): a training video and/or reference
photos for the face, a voice sample for cloning, and a recorded consent from
the actual person being represented. No avatar/voice generation happens here —
M3 reads this record to run the GPU inference; this module only owns identity,
media, and consent.

Consent is a first-class, immutable record (``PersonaConsent``), not a boolean
flag — capturing who granted it, when, under what policy version, and that the
person granting it is a real, distinct action from creating the persona shell.
An identity cannot be used for generation until it has an active consent
record; revoking consent immediately blocks reuse without deleting history.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from enum import StrEnum

import sqlalchemy as sa
from sqlmodel import Field

from app.models.base import JSON, TenantModel


class PersonaIdentityStatus(StrEnum):
    draft = "draft"                  # created, media/consent incomplete
    pending_consent = "pending_consent"  # media uploaded, awaiting consent
    ready = "ready"                  # consented + has usable media — M3 may train on it
    revoked = "revoked"              # consent withdrawn — never usable again


class PersonaIdentity(TenantModel, table=True):
    __tablename__ = "persona_identities"

    brand_id: uuid.UUID | None = Field(default=None, foreign_key="brands.id", index=True)
    buyer_persona_id: uuid.UUID | None = Field(default=None, foreign_key="buyer_personas.id")

    name: str = Field(max_length=200)                 # e.g. "Jordan (Founder)"
    description: str | None = Field(default=None, sa_type=sa.Text)
    status: PersonaIdentityStatus = Field(
        default=PersonaIdentityStatus.draft, sa_type=sa.String(20), index=True,
    )

    # Physical/voice descriptors — customizable, used to steer generation and to
    # sanity-check that generated output matches the described person.
    appearance_notes: str | None = Field(default=None, sa_type=sa.Text)
    voice_notes: str | None = Field(default=None, sa_type=sa.Text)   # accent, pitch, pace, tone

    # Media (storage keys — see storage_service). Populated via the upload
    # endpoints; never overwritten in place, only replaced wholesale.
    training_video_path: str | None = Field(default=None, max_length=600)
    voice_sample_path: str | None = Field(default=None, max_length=600)
    reference_image_paths: list = Field(default_factory=list, sa_type=JSON)

    # Filled in later by M3 once a self-hosted voice/avatar model is trained on
    # this identity's media. Absent here = nothing trained yet.
    voice_model_ref: str | None = Field(default=None, max_length=500)
    avatar_model_ref: str | None = Field(default=None, max_length=500)

    created_by: uuid.UUID = Field(foreign_key="admin_users.id", index=True)


class PersonaConsent(TenantModel, table=True):
    """Immutable consent record for one PersonaIdentity. Never edited — a
    revocation is a new row (is_active=False on the prior one is the effect;
    the record of what was granted is preserved for audit)."""

    __tablename__ = "persona_consents"

    persona_identity_id: uuid.UUID = Field(foreign_key="persona_identities.id", index=True)

    # The real person's own attestation — who is granting rights to their likeness.
    subject_name: str = Field(max_length=200)
    subject_email: str = Field(max_length=320)
    # Freeform statement the subject typed/signed (not just a checkbox), plus
    # the policy text version they agreed to, so consent scope is auditable.
    consent_statement: str = Field(sa_type=sa.Text)
    policy_version: str = Field(max_length=40)

    granted_by: uuid.UUID = Field(foreign_key="admin_users.id", index=True)  # who recorded it
    granted_at: datetime | None = Field(default=None)
    revoked_at: datetime | None = Field(default=None)
    revoked_by: uuid.UUID | None = Field(default=None, foreign_key="admin_users.id")
    is_active: bool = Field(default=True, index=True)
