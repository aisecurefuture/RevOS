"""RevOS data models.

Importing this package registers every table on ``SQLModel.metadata`` — which
is what Alembic autogenerate and ``create_all`` rely on. Import order respects
Python-level symbol dependencies (FK strings are resolved later by SQLAlchemy).
"""

from app.models.analytics import (
    ConversionGoal,
    Event,
    RevenueGoal,
    RevenueRecord,
    RevenueStatus,
    UTMLink,
)
from app.models.approval import ApprovalAction, ApprovalRequest, ApprovalStatus
from app.models.base import BaseModel, IDModel, TimestampModel, utcnow
from app.models.brand import Audience, Brand, BrandType, BrandVoice, BuyerPersona
from app.models.campaign import (
    Campaign,
    CampaignChannel,
    CampaignStatus,
    Form,
    FormSubmission,
    FormType,
    LandingPage,
)
from app.models.content import (
    CTA,
    ContentCalendar,
    ContentChannel,
    ContentItem,
    ContentState,
    Hashtag,
    Hook,
    Pillar,
)
from app.models.crm import (
    Company,
    Contact,
    Deal,
    DealStatus,
    LifecycleStage,
    Note,
    PipelineStage,
    Task,
    TaskStatus,
)
from app.models.email import (
    EmailCategory,
    EmailMessage,
    EmailStatus,
    EmailTemplate,
    SenderIdentity,
    Suppression,
    SuppressionReason,
)
from app.models.lead import (
    ConsentRecord,
    ConsentStatus,
    Lead,
    LeadTagLink,
    Segment,
    Tag,
    UTMCapture,
)
from app.models.media import MediaAsset, MediaKind, MediaStatus, MediaVariant
from app.models.offer import Offer, OfferStatus, OfferType
from app.models.sequence import (
    ABTest,
    Enrollment,
    EnrollmentStatus,
    Sequence,
    SequenceStatus,
    SequenceStep,
    SequenceType,
    StepRun,
    StepRunStatus,
)
from app.models.social import (
    SocialAccount,
    SocialCampaign,
    SocialCampaignStatus,
    SocialPlatform,
    SocialPost,
)
from app.models.user import AdminUser, ApiKey, AuditLog, Role

__all__ = [
    # base
    "BaseModel", "IDModel", "TimestampModel", "utcnow",
    # user
    "AdminUser", "ApiKey", "AuditLog", "Role",
    # brand
    "Brand", "BrandType", "BrandVoice", "Audience", "BuyerPersona",
    # offer
    "Offer", "OfferType", "OfferStatus",
    # crm
    "Company", "Contact", "PipelineStage", "Deal", "DealStatus", "Note",
    "Task", "TaskStatus", "LifecycleStage",
    # lead
    "Lead", "ConsentStatus", "ConsentRecord", "Tag", "LeadTagLink", "Segment",
    "UTMCapture",
    # sequence
    "Sequence", "SequenceType", "SequenceStatus", "SequenceStep", "ABTest",
    "Enrollment", "EnrollmentStatus", "StepRun", "StepRunStatus",
    # campaign
    "Campaign", "CampaignStatus", "CampaignChannel", "LandingPage", "Form",
    "FormType", "FormSubmission",
    # email
    "SenderIdentity", "EmailTemplate", "EmailMessage", "EmailCategory",
    "EmailStatus", "Suppression", "SuppressionReason",
    # content
    "ContentItem", "ContentState", "ContentChannel", "ContentCalendar",
    "Pillar", "Hook", "CTA", "Hashtag",
    # social
    "SocialAccount", "SocialCampaign", "SocialCampaignStatus", "SocialPost",
    "SocialPlatform",
    # analytics
    "Event", "UTMLink", "ConversionGoal", "RevenueRecord", "RevenueGoal",
    "RevenueStatus",
    # approval
    "ApprovalRequest", "ApprovalAction", "ApprovalStatus",
    # media
    "MediaAsset", "MediaVariant", "MediaKind", "MediaStatus",
]
