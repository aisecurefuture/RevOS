// Shared types mirroring the backend API contracts.

export type Role = "owner" | "admin" | "editor" | "viewer";

export interface User {
  id: string;
  email: string;
  full_name: string;
  role: Role;
  is_active: boolean;
  totp_enabled: boolean;
  email_verified: boolean;
  is_platform_admin?: boolean;
  timezone?: string | null;
  avatar_url?: string | null;
}

export interface LoginResponse {
  user: User;
  csrf_token: string;
}

export interface Brand {
  id: string;
  name: string;
  slug: string;
  brand_type: string;
  industry?: string | null;
  website_url?: string | null;
  tagline?: string | null;
  description?: string | null;
  is_active: boolean;
}

export type OfferType =
  | "product"
  | "book"
  | "service"
  | "lead_magnet"
  | "course"
  | "consulting"
  | "digital";

export interface Offer {
  id: string;
  brand_id: string;
  offer_type: OfferType;
  name: string;
  slug: string;
  subtitle?: string | null;
  status: string;
  price_cents?: number | null;
  currency: string;
}

export type CampaignChannel = "email" | "social" | "landing" | "multi" | "ads";

export interface Campaign {
  id: string;
  brand_id: string;
  name: string;
  slug: string;
  objective?: string | null;
  status: string;
  channel: CampaignChannel;
}

export type ConsentStatus =
  | "none"
  | "single_optin"
  | "pending_double_optin"
  | "confirmed"
  | "unsubscribed";

export interface Lead {
  id: string;
  brand_id: string;
  email: string;
  first_name?: string | null;
  last_name?: string | null;
  company_name?: string | null;
  source?: string | null;
  consent_status: ConsentStatus;
  lead_score: number;
  created_at: string;
}

export interface Form {
  id: string;
  brand_id: string;
  name: string;
  slug: string;
  form_type: string;
  consent_required: boolean;
  double_optin: boolean;
  embed_enabled: boolean;
  is_active: boolean;
}

export interface EmailMessage {
  id: string;
  to_email: string;
  subject: string;
  category: string;
  status: string;
  test_mode: boolean;
  open_count: number;
  click_count: number;
  created_at: string;
}

export interface Approval {
  id: string;
  action_type: string;
  status: string;
  title: string;
  summary?: string | null;
  risk_notes?: string | null;
  entity_type?: string | null;
  entity_id?: string | null;
  payload?: Record<string, unknown>;
  created_at: string;
}

export interface SequenceStep {
  id: string;
  name: string;
  order_index: number;
  delay_minutes: number;
  subject?: string | null;
  require_approval: boolean;
  is_active: boolean;
}

export interface Sequence {
  id: string;
  brand_id: string;
  name: string;
  slug: string;
  sequence_type: string;
  status: string;
  goal_event?: string | null;
  require_approval: boolean;
  steps?: SequenceStep[];
}

export interface TickResult {
  processed: number;
  sent: number;
  completed: number;
  awaiting_approval: number;
  stopped: number;
}

export interface ContactChannel {
  value: string;
  label?: string | null;
  is_primary: boolean;
}

export interface Contact {
  id: string;
  first_name?: string | null;
  last_name?: string | null;
  email?: string | null;
  phone?: string | null;
  emails?: ContactChannel[];
  phones?: ContactChannel[];
  title?: string | null;
  linkedin_url?: string | null;
  notes?: string | null;
  address_line1?: string | null;
  address_line2?: string | null;
  city?: string | null;
  region?: string | null;
  postal_code?: string | null;
  country?: string | null;
  source?: string | null;
  lifecycle_stage: string;
  lead_score: number;
}

// --- Matching engine + marketplace -----------------------------------------
export interface MatchDimension {
  key: string;
  score: number;
  weight: number;
  available: boolean;
  detail: string;
}

export interface MatchScore {
  overall: number;
  coverage: number;
  rationale: string;
  dimensions: MatchDimension[];
}

export interface MatchCreator {
  id: string;
  display_name: string;
  handle?: string | null;
  primary_platform?: string | null;
  industry?: string | null;
  size_tier?: string | null;
  category?: string | null;
  topics?: string[];
  follower_count?: number | null;
  engagement_rate?: number | null;
  discoverable: boolean;
  status: string;
  brand_id?: string | null;
}

export interface MatchProduct {
  id: string;
  name: string;
  industry?: string | null;
  category?: string | null;
  description?: string | null;
  status: string;
  discoverable: boolean;
  brand_id?: string | null;
  offer_id?: string | null;
}

export interface CreatorDiscovery {
  creator: MatchCreator;
  score: MatchScore | null;
}

export interface ProductDiscovery {
  product: MatchProduct;
  score: MatchScore | null;
}

export type CollaborationDirection = "brand_to_creator" | "creator_to_brand";
export type CollaborationStatus =
  | "pending"
  | "accepted"
  | "declined"
  | "withdrawn"
  | "expired";

export interface CollaborationRequest {
  id: string;
  direction: CollaborationDirection;
  status: CollaborationStatus;
  initiator_account_id: string;
  creator_id: string;
  product_id?: string | null;
  message: string;
  response_note?: string | null;
  created_at: string;
}

export interface ReputationDimension {
  key: string;
  score: number;
  weight: number;
  available: boolean;
  detail: string;
}

export interface ReputationScore {
  overall: number;
  coverage: number;
  review_count: number;
  rationale: string;
  dimensions: ReputationDimension[];
}

export interface InsightBenchmark {
  metric: string;
  you: number;
  cohort_avg: number;
  cohort_size: number;
  percentile: number | null;
  verdict: "above" | "below" | "on_par";
}

export interface InsightRecommendation {
  priority: "high" | "medium" | "low";
  title: string;
  detail: string;
}

export interface Insights {
  subject: {
    id: string;
    type: "creator" | "product";
    name: string;
    industry?: string | null;
    industry_category?: string | null;
    size_tier?: string | null;
  };
  reputation: ReputationScore;
  metrics: Record<string, number | null>;
  benchmarks: InsightBenchmark[];
  recommendations: InsightRecommendation[];
}

export type CollaborationKind = "one_off" | "ambassador";
export type CollaborationState = "active" | "paused" | "completed" | "ended";

export interface Collaboration {
  id: string;
  collaboration_request_id: string;
  brand_account_id: string;
  creator_account_id: string;
  creator_id: string;
  product_id?: string | null;
  kind: CollaborationKind;
  state: CollaborationState;
  title?: string | null;
  ended_at?: string | null;
  created_at: string;
}

export interface CollaborationShare {
  id: string;
  collaboration_id: string;
  shared_by_account_id: string;
  resource_type: string;
  resource_id: string;
  scope?: string | null;
  expires_at?: string | null;
  revoked_at?: string | null;
  status: "active" | "revoked" | "expired";
  created_at: string;
}

export interface SharedBrandBook {
  brand_id: string;
  mission?: string | null;
  vision?: string | null;
  positioning?: string | null;
  elevator_pitch?: string | null;
  target_summary?: string | null;
  key_messages: unknown[];
  core_values: unknown[];
  brand_story?: string | null;
  voice_spectrum: Record<string, number>;
  banned_terms: string[];
  required_disclaimers: string[];
  is_published: boolean;
}

export type AssetKind = "text" | "image" | "video";
export type AssetState = "draft" | "in_review" | "changes_requested" | "approved" | "published";
export type ApprovalDecision = "approved" | "changes_requested";

export interface CollaborationAsset {
  id: string;
  collaboration_id: string;
  created_by_account_id: string;
  kind: AssetKind;
  title?: string | null;
  current_version: number;
  state: AssetState;
  linked_social_post_id?: string | null;
  created_at: string;
}

export interface AssetVersion {
  id: string;
  asset_id: string;
  version: number;
  created_by_account_id: string;
  caption?: string | null;
  media_urls: string[];
  created_at: string;
}

export interface AssetComment {
  id: string;
  asset_id: string;
  version?: number | null;
  author_account_id: string;
  author_user_id: string;
  body: string;
  created_at: string;
}

export interface AssetApproval {
  id: string;
  asset_id: string;
  version: number;
  account_id: string;
  user_id: string;
  decision: ApprovalDecision;
  note?: string | null;
  created_at: string;
}

export interface CollaborationBrief {
  id: string;
  collaboration_id: string;
  updated_by_account_id: string;
  goals?: string | null;
  key_messages: string[];
  dos: string[];
  donts: string[];
  deadline?: string | null;
  requires_disclosure: boolean;
  disclosure_text?: string | null;
  usage_rights?: string | null;
  usage_duration_days?: number | null;
  whitelisting_allowed: boolean;
  boost_allowed: boolean;
  created_at: string;
  updated_at: string;
}

export type DeliverableStatus = "pending" | "in_progress" | "delivered" | "approved";

export interface Deliverable {
  id: string;
  collaboration_id: string;
  created_by_account_id: string;
  title: string;
  description?: string | null;
  due_at?: string | null;
  status: DeliverableStatus;
  asset_id?: string | null;
  completed_at?: string | null;
  created_at: string;
}

export interface CollaborationMessage {
  id: string;
  collaboration_id: string;
  sender_account_id: string;
  sender_user_id: string;
  body: string;
  is_flagged: boolean;
  flagged_reason?: string | null;
  flagged_at?: string | null;
  created_at: string;
}

export interface PipelineStage {
  id: string;
  name: string;
  slug: string;
  order_index: number;
  is_won: boolean;
  is_lost: boolean;
}

export interface Deal {
  id: string;
  name: string;
  pipeline_stage_id?: string | null;
  amount_cents?: number | null;
  currency: string;
  status: string;
}

export interface ContactImportResult {
  created: number;
  updated: number;
  skipped: number;
  companies_created: number;
  note: string;
}

export interface ContentItem {
  id: string;
  channel: string;
  title: string;
  body?: string | null;
  state: string;
  scheduled_at?: string | null;
  published_at?: string | null;
}

export interface SocialCampaign {
  id: string;
  name: string;
  objective?: string | null;
  theme?: string | null;
  platforms: string[];
  status: string;
}

export interface SocialPost {
  id: string;
  platform: string;
  caption?: string | null;
  hashtags: string[];
  state: string;
  scheduled_at?: string | null;
  external_post_id?: string | null;
}

export interface PublishResult {
  published: boolean;
  mode: string;
  message: string;
  external_id?: string | null;
}

export interface MediaVariant {
  id: string;
  media_asset_id: string;
  platform: string;
  purpose: string;
  aspect_ratio?: string | null;
  width?: number | null;
  height?: number | null;
  format?: string | null;
  is_ai_enhanced: boolean;
  state: string;
}

export interface MediaAsset {
  id: string;
  kind: string;
  original_filename: string;
  width?: number | null;
  height?: number | null;
  status: string;
  variants?: MediaVariant[];
}

export interface IntegrationStatus {
  email: boolean;
  email_live: boolean;
  ai: boolean;
  stripe: boolean;
  s3: boolean;
  social: Record<string, boolean>;
  analytics: {
    plausible_domain: string | null;
    posthog_key: string | null;
    posthog_host: string;
    ga_measurement_id: string | null;
  };
}

export interface AnalyticsOverview {
  revenue_mtd_cents: number;
  new_leads_30d: number;
  subscribers: number;
  pipeline_value_cents: number;
  pending_approvals: number;
  leads_by_source: { source: string; count: number }[];
  email: { sent: number; opened: number; clicked: number; open_rate: number; click_rate: number };
  funnel: { stage: string; count: number }[];
  recent_activity: { action: string; entity_type: string | null; at: string }[];
}


export interface ApiError {
  error: { code: string; message: string; details?: unknown };
}
