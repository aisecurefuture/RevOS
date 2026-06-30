// Shared types mirroring the backend API contracts.

export type Role = "owner" | "admin" | "editor" | "viewer";

export interface User {
  id: string;
  email: string;
  full_name: string;
  role: Role;
  is_active: boolean;
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

export interface Contact {
  id: string;
  first_name?: string | null;
  last_name?: string | null;
  email?: string | null;
  title?: string | null;
  linkedin_url?: string | null;
  source?: string | null;
  lifecycle_stage: string;
  lead_score: number;
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
  calendly: boolean;
  notion: boolean;
  zapier: boolean;
  bitly: boolean;
  google_sheets: boolean;
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
