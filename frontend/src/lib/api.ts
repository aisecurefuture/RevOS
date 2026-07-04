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

export const billingApi = {
  status: () => apiFetch<BillingStatus>("/billing/status"),
  startTrial: () => apiFetch<BillingStatus>("/billing/start-trial", { method: "POST" }),
  checkout: (plan: "pro" | "agency", interval: "monthly" | "annual") =>
    apiFetch<{ checkout_url: string }>("/billing/checkout", {
      method: "POST",
      body: JSON.stringify({ plan, interval }),
    }),
  portal: () =>
    apiFetch<{ portal_url: string }>("/billing/portal", {
      method: "POST",
    }),
};
