// Same-origin API client (requests are proxied to FastAPI by next.config.js).
//
// Auth uses HttpOnly cookies set by the backend; this client adds the
// double-submit CSRF token (read from the readable `revos_csrf` cookie) on all
// state-changing requests.

import type { LoginResponse, User } from "./types";

const CSRF_COOKIE = "revos_csrf";
const CSRF_HEADER = "X-CSRF-Token";
const UNSAFE = new Set(["POST", "PUT", "PATCH", "DELETE"]);

export class ApiError extends Error {
  code: string;
  status: number;
  details?: unknown;

  constructor(status: number, code: string, message: string, details?: unknown) {
    super(message);
    this.status = status;
    this.code = code;
    this.details = details;
  }
}

function readCookie(name: string): string | null {
  if (typeof document === "undefined") return null;
  const match = document.cookie.match(new RegExp("(^|; )" + name + "=([^;]*)"));
  return match ? decodeURIComponent(match[2]) : null;
}

export async function apiFetch<T>(path: string, init: RequestInit = {}): Promise<T> {
  const method = (init.method || "GET").toUpperCase();
  const headers = new Headers(init.headers);
  if (init.body && !headers.has("Content-Type")) {
    headers.set("Content-Type", "application/json");
  }
  if (UNSAFE.has(method)) {
    const csrf = readCookie(CSRF_COOKIE);
    if (csrf) headers.set(CSRF_HEADER, csrf);
  }

  const resp = await fetch(`/api${path}`, {
    ...init,
    method,
    headers,
    credentials: "same-origin",
  });

  if (resp.status === 204) return undefined as T;

  const data = await resp.json().catch(() => null);
  if (!resp.ok) {
    const err = data?.error;
    throw new ApiError(
      resp.status,
      err?.code ?? "error",
      err?.message ?? "Request failed",
      err?.details,
    );
  }
  return data as T;
}

export async function apiUpload<T>(path: string, formData: FormData): Promise<T> {
  const headers = new Headers();
  const csrf = readCookie(CSRF_COOKIE);
  if (csrf) headers.set(CSRF_HEADER, csrf);
  // Do NOT set Content-Type — the browser adds the multipart boundary.
  const resp = await fetch(`/api${path}`, {
    method: "POST",
    headers,
    body: formData,
    credentials: "same-origin",
  });
  const data = await resp.json().catch(() => null);
  if (!resp.ok) {
    const err = data?.error;
    throw new ApiError(resp.status, err?.code ?? "error", err?.message ?? "Upload failed");
  }
  return data as T;
}


// --- Auth endpoints ---------------------------------------------------------
export const authApi = {
  login: (email: string, password: string) =>
    apiFetch<LoginResponse>("/auth/login", {
      method: "POST",
      body: JSON.stringify({ email, password }),
    }),
  register: (email: string, password: string, full_name: string) =>
    apiFetch<LoginResponse>("/auth/register", {
      method: "POST",
      body: JSON.stringify({ email, password, full_name }),
    }),
  me: () => apiFetch<User>("/auth/me"),
  logout: () => apiFetch<{ status: string }>("/auth/logout", { method: "POST" }),
  refresh: () => apiFetch<LoginResponse>("/auth/refresh", { method: "POST" }),
  changePassword: (current_password: string, new_password: string) =>
    apiFetch<{ status: string }>("/auth/password", {
      method: "POST",
      body: JSON.stringify({ current_password, new_password }),
    }),
  acceptInvitation: (token: string) =>
    apiFetch<{ account_id: string; role: string }>("/auth/invitation/accept", {
      method: "POST",
      body: JSON.stringify({ token }),
    }),
  verifyEmail: (token: string) =>
    apiFetch<{ status: string; email: string }>(`/auth/verify-email?token=${encodeURIComponent(token)}`),
  resendVerification: () =>
    apiFetch<{ status: string }>("/auth/verify-email/resend", { method: "POST" }),
};

// --- Accounts / team membership / invitations -------------------------------
export interface AccountOut {
  id: string;
  type: string;
  name: string;
  slug: string;
}

export interface MembershipOut {
  account: AccountOut;
  role: string;
  is_active: boolean;
}

export interface MemberOut {
  user_id: string;
  email: string;
  full_name: string;
  role: string;
}

export interface InvitationOut {
  id: string;
  email: string;
  role: string;
  created_at: string;
}

export interface InvitationCreatedOut extends InvitationOut {
  token: string;
  accept_url: string;
}

export const accountsApi = {
  list: () => apiFetch<MembershipOut[]>("/accounts"),
  createTeam: (name: string) =>
    apiFetch<AccountOut>("/accounts", { method: "POST", body: JSON.stringify({ name }) }),
  switchAccount: (account_id: string) =>
    apiFetch<{ account_id: string; role: string; csrf_token: string }>("/accounts/switch", {
      method: "POST", body: JSON.stringify({ account_id }),
    }),
  listMembers: (accountId: string) => apiFetch<MemberOut[]>(`/accounts/${accountId}/members`),
  changeMemberRole: (accountId: string, userId: string, role: string) =>
    apiFetch<MemberOut>(`/accounts/${accountId}/members/${userId}`, {
      method: "PATCH", body: JSON.stringify({ role }),
    }),
  removeMember: (accountId: string, userId: string) =>
    apiFetch<void>(`/accounts/${accountId}/members/${userId}`, { method: "DELETE" }),
  listInvitations: (accountId: string) =>
    apiFetch<InvitationOut[]>(`/accounts/${accountId}/invitations`),
  inviteMember: (accountId: string, email: string, role: string) =>
    apiFetch<InvitationCreatedOut>(`/accounts/${accountId}/invitations`, {
      method: "POST", body: JSON.stringify({ email, role }),
    }),
  revokeInvitation: (accountId: string, inviteId: string) =>
    apiFetch<void>(`/accounts/${accountId}/invitations/${inviteId}`, { method: "DELETE" }),
};

// --- Billing endpoints ------------------------------------------------------
export interface BillingStatus {
  plan: string;
  effective_plan: string | null;
  status: string | null;
  trial_ends_at: string | null;
  current_period_end: string | null;
  is_trial_expired: boolean;
  cancel_at_period_end: boolean;
  billing_interval: string | null;
  limits: {
    seats: number | null;
    brands: number | null;
    contacts: number | null;
    emails_per_month: number | null;
    social_connections: number | null;
    ai_drafts_per_month: number | null;
    landing_pages: number | null;
    api_access: boolean;
    client_workspaces: boolean;
    white_label: boolean;
  };
  prices: {
    pro_monthly_cents: number;
    pro_annual_cents: number;
    agency_monthly_cents: number;
    agency_annual_cents: number;
  };
}

// --- Social connections ------------------------------------------------------
export interface SocialConnection {
  id: string;
  platform: "facebook" | "instagram" | "threads" | "youtube" | "twitter" | "linkedin" | "tiktok";
  external_id: string;
  handle: string | null;
  display_name: string | null;
  status: "active" | "error" | "expired" | "revoked";
  expires_at: string | null;
  created_at: string;
}

export const socialApi = {
  list: () => apiFetch<SocialConnection[]>("/social/connections"),
  connectUrl: (platform: string) =>
    apiFetch<{ url: string }>(`/social/connections/connect-url?platform=${platform}`),
  disconnect: (id: string) =>
    apiFetch<void>(`/social/connections/${id}`, { method: "DELETE" }),
};

// --- Automation (auto-approve autopilot) -------------------------------------
export interface AutoApproveStatus {
  enabled: boolean;
  until: string | null;
  indefinite: boolean;
}

export const automationApi = {
  getAutoApprove: () => apiFetch<AutoApproveStatus>("/automation/auto-approve"),
  setAutoApprove: (enabled: boolean, durationHours: number | null) =>
    apiFetch<AutoApproveStatus>("/automation/auto-approve", {
      method: "POST",
      body: JSON.stringify({ enabled, duration_hours: durationHours }),
    }),
};

// --- Connected apps (per-account low-cost integrations) ---------------------
export interface IntegrationCredential {
  provider: "calendly" | "notion" | "bitly" | "zapier" | "google_sheets";
  config: Record<string, unknown>;
  status: string;
}

export interface ZapierSaveResult {
  credential: IntegrationCredential;
  inbound_webhook_url: string;
  inbound_secret: string | null;
}

export const integrationCredentialsApi = {
  list: () => apiFetch<IntegrationCredential[]>("/integrations/credentials"),
  saveCalendly: (schedulingUrl: string) =>
    apiFetch<IntegrationCredential>("/integrations/credentials/calendly", {
      method: "POST",
      body: JSON.stringify({ scheduling_url: schedulingUrl }),
    }),
  saveNotion: (apiKey: string, databaseId: string) =>
    apiFetch<IntegrationCredential>("/integrations/credentials/notion", {
      method: "POST",
      body: JSON.stringify({ api_key: apiKey, database_id: databaseId }),
    }),
  saveBitly: (accessToken: string) =>
    apiFetch<IntegrationCredential>("/integrations/credentials/bitly", {
      method: "POST",
      body: JSON.stringify({ access_token: accessToken }),
    }),
  saveGoogleSheets: (serviceAccountJson: string, spreadsheetId: string) =>
    apiFetch<IntegrationCredential>("/integrations/credentials/google-sheets", {
      method: "POST",
      body: JSON.stringify({ service_account_json: serviceAccountJson, spreadsheet_id: spreadsheetId }),
    }),
  saveZapier: (outboundWebhookUrl: string | null) =>
    apiFetch<ZapierSaveResult>("/integrations/credentials/zapier", {
      method: "POST",
      body: JSON.stringify({ outbound_webhook_url: outboundWebhookUrl }),
    }),
  regenerateZapierSecret: () =>
    apiFetch<{ inbound_secret: string }>("/integrations/credentials/zapier/regenerate-secret", {
      method: "POST",
    }),
  remove: (provider: string) =>
    apiFetch<void>(`/integrations/credentials/${provider}`, { method: "DELETE" }),
  shortenLink: (url: string) =>
    apiFetch<{ short_url: string }>("/integrations/bitly/shorten", {
      method: "POST",
      body: JSON.stringify({ url }),
    }),
  pushContactsToNotion: (brandId?: string | null) =>
    apiFetch<{ pushed: number }>(
      `/integrations/notion/push-contacts${brandId ? `?brand_id=${brandId}` : ""}`,
      { method: "POST" },
    ),
  pushContactsToSheets: (brandId?: string | null) =>
    apiFetch<{ pushed: number }>(
      `/integrations/google-sheets/push-contacts${brandId ? `?brand_id=${brandId}` : ""}`,
      { method: "POST" },
    ),
};

// --- Scheduler --------------------------------------------------------------
export interface AvailabilityWindow {
  weekday: number; // Mon=0 .. Sun=6
  start: string;   // "HH:MM"
  end: string;
}

export interface EventType {
  id: string;
  name: string;
  slug: string;
  description: string | null;
  duration_minutes: number;
  buffer_before_minutes: number;
  buffer_after_minutes: number;
  min_notice_minutes: number;
  max_days_ahead: number;
  timezone: string;
  weekly_availability: AvailabilityWindow[];
  location_type: "custom" | "phone" | "in_person";
  location_detail: string | null;
  active: boolean;
}

export interface SchedulerBooking {
  id: string;
  event_type_id: string;
  invitee_name: string;
  invitee_email: string;
  invitee_timezone: string;
  invitee_notes: string | null;
  start_at: string;
  end_at: string;
  status: string;
  location_type: string;
  location_detail: string | null;
}

export interface PublicEventType {
  id: string;
  name: string;
  description: string | null;
  duration_minutes: number;
  timezone: string;
  location_type: string;
}

export interface PublicBooking {
  event_type_id: string;
  invitee_name: string;
  invitee_email: string;
  invitee_timezone: string;
  start_at: string;
  end_at: string;
  status: string;
  location_type: string;
  location_detail: string | null;
  manage_token: string;
}

export const schedulerApi = {
  listEventTypes: () => apiFetch<EventType[]>("/scheduler/event-types"),
  createEventType: (data: Partial<EventType>) =>
    apiFetch<EventType>("/scheduler/event-types", { method: "POST", body: JSON.stringify(data) }),
  updateEventType: (id: string, data: Partial<EventType>) =>
    apiFetch<EventType>(`/scheduler/event-types/${id}`, { method: "PATCH", body: JSON.stringify(data) }),
  deleteEventType: (id: string) =>
    apiFetch<void>(`/scheduler/event-types/${id}`, { method: "DELETE" }),
  listBookings: (upcomingOnly = false) =>
    apiFetch<SchedulerBooking[]>(`/scheduler/bookings${upcomingOnly ? "?upcoming_only=true" : ""}`),
};

export const publicSchedulerApi = {
  getEvent: (id: string) => apiFetch<PublicEventType>(`/public/scheduler/event/${id}`),
  getSlots: (id: string, from: string, to: string) =>
    apiFetch<{ timezone: string; duration_minutes: number; slots: string[] }>(
      `/public/scheduler/event/${id}/slots?from=${from}&to=${to}`,
    ),
  book: (id: string, body: {
    start_at: string; invitee_name: string; invitee_email: string;
    invitee_timezone: string; invitee_notes?: string;
  }) => apiFetch<PublicBooking>(`/public/scheduler/event/${id}/book`, {
    method: "POST", body: JSON.stringify(body),
  }),
  getBooking: (token: string) => apiFetch<PublicBooking>(`/public/scheduler/booking/${token}`),
  cancel: (token: string) =>
    apiFetch<PublicBooking>(`/public/scheduler/booking/${token}/cancel`, { method: "POST" }),
  reschedule: (token: string, startAt: string) =>
    apiFetch<PublicBooking>(`/public/scheduler/booking/${token}/reschedule`, {
      method: "POST", body: JSON.stringify({ start_at: startAt }),
    }),
};

// --- Brand Book -------------------------------------------------------------
export interface CoreValue {
  value: string;
  statement?: string | null;
  example?: string | null;
}

export interface VoiceSpectrum {
  humor?: number;      // 1 funny .. 5 serious
  energy?: number;      // 1 matter-of-fact .. 5 enthusiastic
  formality?: number;   // 1 formal .. 5 casual
  convention?: number;  // 1 conventional .. 5 quirky
}

export const BRAND_ARCHETYPES = [
  "innocent", "explorer", "sage", "hero", "outlaw", "magician",
  "regular_guy", "lover", "jester", "caregiver", "ruler", "creator",
];

export interface BrandBook {
  id: string;
  brand_id: string;
  mission: string | null;
  vision: string | null;
  positioning: string | null;
  elevator_pitch: string | null;
  target_summary: string | null;
  audience_exclusions: string | null;
  key_messages: string[];
  core_values: CoreValue[];
  brand_story: string | null;
  brand_archetype: string | null;
  voice_spectrum: VoiceSpectrum;
  banned_terms: string[];
  required_disclaimers: string[];
  compliance_notes: string | null;
  competitors: string[];
  is_published: boolean;
}

export interface BrandClaim {
  id: string;
  claim: string;
  proof: string | null;
  category: string;
  approved: boolean;
  expires_at: string | null;
}

export interface BrandFact {
  id: string;
  topic: string;
  content: string;
  category: string | null;
  source: string | null;
}

export interface ContentCheck {
  passed: boolean;
  blocked: boolean;
  banned_hits: string[];
  missing_disclaimers: string[];
  unverified_numbers: string[];
  llm_checked: boolean;
  unsupported_claims: string[];
  llm_error: string | null;
}

export const brandBookApi = {
  get: (brandId: string) => apiFetch<BrandBook>(`/brand-book/${brandId}`),
  update: (brandId: string, data: Partial<BrandBook>) =>
    apiFetch<BrandBook>(`/brand-book/${brandId}`, { method: "PATCH", body: JSON.stringify(data) }),
  listClaims: (brandId: string) => apiFetch<BrandClaim[]>(`/brand-book/${brandId}/claims`),
  addClaim: (brandId: string, data: { claim: string; proof?: string; category?: string }) =>
    apiFetch<BrandClaim>(`/brand-book/${brandId}/claims`, { method: "POST", body: JSON.stringify(data) }),
  deleteClaim: (brandId: string, id: string) =>
    apiFetch<void>(`/brand-book/${brandId}/claims/${id}`, { method: "DELETE" }),
  listFacts: (brandId: string) => apiFetch<BrandFact[]>(`/brand-book/${brandId}/facts`),
  addFact: (brandId: string, data: { topic: string; content: string; source?: string }) =>
    apiFetch<BrandFact>(`/brand-book/${brandId}/facts`, { method: "POST", body: JSON.stringify(data) }),
  deleteFact: (brandId: string, id: string) =>
    apiFetch<void>(`/brand-book/${brandId}/facts/${id}`, { method: "DELETE" }),
  check: (brandId: string, text: string) =>
    apiFetch<ContentCheck>(`/brand-book/${brandId}/check`, {
      method: "POST", body: JSON.stringify({ text }),
    }),
};

// --- Content autopilot ------------------------------------------------------
export interface AutopilotConfig {
  brand_id: string;
  enabled: boolean;
  auto_publish: boolean;
  platforms: string[];
  posts_per_run: number;
  run_interval_hours: number;
  content_themes: string[];
  default_cta: string | null;
  last_run_at: string | null;
}

export interface AutopilotRun {
  generated: number;
  published: number;
  queued: number;
  blocked: number;
  skipped: number;
}

export const autopilotApi = {
  get: (brandId: string) => apiFetch<AutopilotConfig>(`/autopilot/${brandId}`),
  update: (brandId: string, data: Partial<AutopilotConfig>) =>
    apiFetch<AutopilotConfig>(`/autopilot/${brandId}`, { method: "PATCH", body: JSON.stringify(data) }),
  run: (brandId: string) =>
    apiFetch<AutopilotRun>(`/autopilot/${brandId}/run`, { method: "POST" }),
};

// --- Persona identity (avatar likeness + voice + consent) --------------------
export interface PersonaIdentity {
  id: string;
  brand_id: string | null;
  buyer_persona_id: string | null;
  name: string;
  description: string | null;
  status: "draft" | "pending_consent" | "ready" | "revoked";
  appearance_notes: string | null;
  voice_notes: string | null;
  training_video_path: string | null;
  voice_sample_path: string | null;
  reference_image_paths: string[];
  voice_model_ref: string | null;
  avatar_model_ref: string | null;
  // Ephemeral — only present on the upload-voice-sample response.
  voice_sample_warning?: string | null;
}

export interface PersonaConsent {
  id: string;
  subject_name: string;
  subject_email: string;
  consent_statement: string;
  policy_version: string;
  granted_at: string | null;
  revoked_at: string | null;
  is_active: boolean;
}

export const personaApi = {
  list: (brandId?: string | null) =>
    apiFetch<PersonaIdentity[]>(`/personas${brandId ? `?brand_id=${brandId}` : ""}`),
  get: (id: string) => apiFetch<PersonaIdentity>(`/personas/${id}`),
  create: (data: { name: string; brand_id?: string | null; description?: string }) =>
    apiFetch<PersonaIdentity>("/personas", { method: "POST", body: JSON.stringify(data) }),
  update: (id: string, data: Partial<PersonaIdentity>) =>
    apiFetch<PersonaIdentity>(`/personas/${id}`, { method: "PATCH", body: JSON.stringify(data) }),
  remove: (id: string) => apiFetch<void>(`/personas/${id}`, { method: "DELETE" }),
  uploadTrainingVideo: (id: string, file: File) => {
    const fd = new FormData();
    fd.append("file", file);
    return apiUpload<PersonaIdentity>(`/personas/${id}/training-video`, fd);
  },
  uploadVoiceSample: (id: string, file: File) => {
    const fd = new FormData();
    fd.append("file", file);
    return apiUpload<PersonaIdentity>(`/personas/${id}/voice-sample`, fd);
  },
  uploadReferenceImage: (id: string, file: File) => {
    const fd = new FormData();
    fd.append("file", file);
    return apiUpload<PersonaIdentity>(`/personas/${id}/reference-images`, fd);
  },
  removeReferenceImage: (id: string, path: string) =>
    apiFetch<PersonaIdentity>(`/personas/${id}/reference-images?path=${encodeURIComponent(path)}`, {
      method: "DELETE",
    }),
  listConsents: (id: string) => apiFetch<PersonaConsent[]>(`/personas/${id}/consents`),
  grantConsent: (id: string, data: { subject_name: string; subject_email: string; consent_statement: string }) =>
    apiFetch<PersonaConsent>(`/personas/${id}/consent`, { method: "POST", body: JSON.stringify(data) }),
  revokeConsent: (id: string) =>
    apiFetch<PersonaIdentity>(`/personas/${id}/consent/revoke`, { method: "POST" }),
};

// --- Avatar video generation ------------------------------------------------
export interface AvatarJob {
  id: string;
  persona_identity_id: string;
  brand_id: string | null;
  script: string;
  target_seconds: number;
  status: "queued" | "processing" | "succeeded" | "failed" | "cancelled";
  estimated_seconds: number | null;
  error: string | null;
  started_at: string | null;
  finished_at: string | null;
  created_at: string;
  has_output: boolean;
}

export interface AvatarDuration {
  seconds: number;
  estimated_seconds: number;
}

export const avatarApi = {
  durations: () => apiFetch<{ durations: AvatarDuration[] }>("/avatar/durations"),
  listJobs: (personaId?: string) =>
    apiFetch<AvatarJob[]>(`/avatar/jobs${personaId ? `?persona_identity_id=${personaId}` : ""}`),
  createJob: (data: { persona_identity_id: string; script: string; target_seconds: number }) =>
    apiFetch<AvatarJob>("/avatar/jobs", { method: "POST", body: JSON.stringify(data) }),
  getJob: (id: string) => apiFetch<AvatarJob>(`/avatar/jobs/${id}`),
  videoUrl: (id: string) => `/api/avatar/jobs/${id}/video`,
  publish: (id: string, data: { platform: string; caption?: string; burn_captions?: boolean }) =>
    apiFetch<{ post_id: string; approval_request_id: string; platform: string }>(
      `/avatar/jobs/${id}/publish`, { method: "POST", body: JSON.stringify(data) },
    ),
};

// --- Pitch Video Studio ------------------------------------------------------
export interface PitchVideoJob {
  id: string;
  brand_id: string;
  title: string;
  aspect_ratio: string;
  voice_mode: string;
  speaker_name: string | null;
  status: "queued" | "generating_audio" | "rendering" | "succeeded" | "failed" | "cancelled";
  progress_note: string | null;
  estimated_seconds: number | null;
  error: string | null;
  started_at: string | null;
  finished_at: string | null;
  created_at: string;
  has_output: boolean;
}

export const pitchVideoApi = {
  status: () => apiFetch<{ enabled: boolean }>("/pitch-videos/status"),
  stockSpeakers: () => apiFetch<{ speakers: string[] }>("/pitch-videos/stock-speakers"),
  importPptx: (file: File, brandSlug: string, style: "minimal" | "schematic" = "schematic") => {
    const fd = new FormData();
    fd.append("file", file);
    fd.append("brand_slug", brandSlug);
    fd.append("style", style);
    return apiUpload<{ deck_spec: object; ai_drafted: boolean; slides_found: number }>(
      "/pitch-videos/import-pptx", fd,
    );
  },
  listJobs: () => apiFetch<PitchVideoJob[]>("/pitch-videos"),
  createJob: (deckSpec: object) =>
    apiFetch<PitchVideoJob>("/pitch-videos", { method: "POST", body: JSON.stringify({ deck_spec: deckSpec }) }),
  getJob: (id: string) => apiFetch<PitchVideoJob>(`/pitch-videos/${id}`),
  videoUrl: (id: string) => `/api/pitch-videos/${id}/video`,
};

// --- Video script engine ----------------------------------------------------
export interface VideoScript {
  id: string;
  brand_id: string;
  persona_identity_id: string | null;
  target_seconds: number;
  angle: string | null;
  script: string;
  hook: string | null;
  word_count: number;
  passed_gate: boolean;
  gate: {
    passed: boolean;
    blocked: boolean;
    banned_hits: string[];
    unverified_numbers: string[];
    missing_disclaimers: string[];
    llm_checked?: boolean;
    unsupported_claims?: string[];
    llm_error?: string | null;
  };
  created_at: string;
}

export const scriptApi = {
  generate: (data: {
    brand_id: string; target_seconds: number;
    persona_identity_id?: string; angle?: string;
  }) => apiFetch<VideoScript>("/scripts/generate", { method: "POST", body: JSON.stringify(data) }),
  list: (personaId?: string) =>
    apiFetch<VideoScript[]>(`/scripts${personaId ? `?persona_identity_id=${personaId}` : ""}`),
};

export const billingApi = {
  status: () => apiFetch<BillingStatus>("/billing/status"),
  startTrial: () => apiFetch<BillingStatus>("/billing/start-trial", { method: "POST" }),
  checkout: (plan: "pro" | "agency", interval: "monthly" | "annual") =>
    apiFetch<{ checkout_url: string }>("/billing/checkout", {
      method: "POST",
      body: JSON.stringify({ plan, interval }),
    }),
  portal: () =>
    apiFetch<{ portal_url: string }>("/billing/portal", { method: "POST" }),
  cancel: () =>
    apiFetch<BillingStatus>("/billing/cancel", { method: "POST" }),
};
