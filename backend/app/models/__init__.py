"""RevOS data models.

Importing this package registers every table on ``SQLModel.metadata`` — which
is what Alembic autogenerate and ``create_all`` rely on. Import order respects
Python-level symbol dependencies (FK strings are resolved later by SQLAlchemy).
"""

from app.models.account import Account, AccountType, Invitation, Membership
from app.models.billing import PlanName, Subscription, SubscriptionStatus
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
from app.models.autopilot import AutopilotConfig
from app.models.avatar_job import AvatarJobStatus, AvatarVideoJob
from app.models.brand import Audience, Brand, BrandType, BrandVoice, BuyerPersona
from app.models.brand_book import BrandBook, BrandClaim, BrandFact, ClaimCategory
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
from app.models.integration_credential import (
    IntegrationCredential,
    IntegrationCredentialStatus,
    IntegrationProvider,
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
from app.models.listing_video import ListingVideoJob, ListingVideoJobStatus
from app.models.media import MediaAsset, MediaKind, MediaStatus, MediaVariant
from app.models.matching import (
    AudienceSource,
    CollaborationDirection,
    CollaborationRequest,
    CollaborationStatus,
    Creator,
    CreatorManagement,
    CreatorManager,
    CreatorStatus,
    MatchProduct,
    MatchProductStatus,
)
from app.models.offer import Offer, OfferStatus, OfferType
from app.models.pitch_video import PitchVideoJob, PitchVideoJobStatus, PitchVideoVoiceMode
from app.models.reputation import (
    Certification,
    CertificationStatus,
    CertificationSubjectType,
    Review,
    ReviewDirection,
)
from app.models.persona_identity import (
    PersonaConsent,
    PersonaIdentity,
    PersonaIdentityStatus,
)
from app.models.scheduler import (
    Booking,
    BookingStatus,
    EventType,
    LocationType,
)
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
from app.models.social_comment import SocialComment, SocialCommentStatus
from app.models.social_connection import SocialConnection, SocialConnectionStatus
from app.models.video_script import VideoScript
from app.models.user import AdminUser, ApiKey, AuditLog, RecoveryCode, Role

__all__ = [
    # base
    "BaseModel", "IDModel", "TimestampModel", "utcnow",
    # user
    "AdminUser", "ApiKey", "AuditLog", "RecoveryCode", "Role",
    # account / tenancy
    "Account", "AccountType", "Invitation", "Membership",
    # billing
    "PlanName", "Subscription", "SubscriptionStatus",
    # brand
    "Brand", "BrandType", "BrandVoice", "Audience", "BuyerPersona",
    # offer
    "Offer", "OfferType", "OfferStatus",
    # matching
    "Creator", "CreatorManagement", "CreatorStatus", "AudienceSource",
    "CreatorManager", "MatchProduct", "MatchProductStatus",
    "CollaborationRequest", "CollaborationDirection", "CollaborationStatus",
    # reputation
    "Certification", "CertificationStatus", "CertificationSubjectType",
    "Review", "ReviewDirection",
    # pitch video
    "ListingVideoJob", "ListingVideoJobStatus",
    "PitchVideoJob", "PitchVideoJobStatus", "PitchVideoVoiceMode",
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
    "SocialPlatform", "SocialConnection", "SocialConnectionStatus",
    "SocialComment", "SocialCommentStatus",
    # analytics
    "Event", "UTMLink", "ConversionGoal", "RevenueRecord", "RevenueGoal",
    "RevenueStatus",
    # approval
    "ApprovalRequest", "ApprovalAction", "ApprovalStatus",
    # media
    "MediaAsset", "MediaVariant", "MediaKind", "MediaStatus",
    # integration credentials
    "IntegrationCredential", "IntegrationProvider", "IntegrationCredentialStatus",
    # scheduler
    "EventType", "Booking", "BookingStatus", "LocationType",
    # brand book
    "BrandBook", "BrandClaim", "BrandFact", "ClaimCategory",
    # autopilot
    "AutopilotConfig",
    # persona identity
    "PersonaIdentity", "PersonaIdentityStatus", "PersonaConsent",
    # avatar jobs
    "AvatarVideoJob", "AvatarJobStatus",
    # video scripts
    "VideoScript",
]
