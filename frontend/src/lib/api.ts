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
