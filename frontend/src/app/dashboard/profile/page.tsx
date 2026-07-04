"use client";

import { useEffect, useState } from "react";

import { PageHeader } from "@/components/PageHeader";
import { Button } from "@/components/ui/Button";
import { Card, CardTitle } from "@/components/ui/Card";
import { ApiError, apiFetch, authApi, billingApi, type BillingStatus } from "@/lib/api";
import { useAuth } from "@/lib/auth";

// ---------------------------------------------------------------------------
// Profile section
// ---------------------------------------------------------------------------
function ProfileSection() {
  const { user, refreshUser } = useAuth();
  const [fullName, setFullName] = useState(user?.full_name ?? "");
  const [saving, setSaving] = useState(false);
  const [msg, setMsg] = useState<{ ok: boolean; text: string } | null>(null);

  useEffect(() => {
    if (user) setFullName(user.full_name);
  }, [user]);

  async function save(e: React.FormEvent) {
    e.preventDefault();
    setSaving(true);
    setMsg(null);
    try {
      await apiFetch("/auth/me", {
        method: "PATCH",
        body: JSON.stringify({ full_name: fullName }),
      });
      await refreshUser();
      setMsg({ ok: true, text: "Profile updated." });
    } catch (err) {
      setMsg({ ok: false, text: err instanceof ApiError ? err.message : "Failed to save." });
    } finally {
      setSaving(false);
    }
  }

  return (
    <Card>
      <CardTitle>Profile</CardTitle>
      <form onSubmit={save} className="space-y-4 mt-3">
        <div>
          <label className="mb-1 block text-sm font-medium text-slate-700">Email</label>
          <p className="rounded-lg border border-slate-200 bg-slate-50 px-3 py-2 text-sm text-slate-500">
            {user?.email}
          </p>
        </div>
        <div>
          <label htmlFor="full_name" className="mb-1 block text-sm font-medium text-slate-700">
            Full name
          </label>
          <input
            id="full_name"
            type="text"
            value={fullName}
            onChange={(e) => setFullName(e.target.value)}
            className="w-full rounded-lg border border-slate-300 px-3 py-2 text-sm focus:border-brand focus:outline-none focus:ring-1 focus:ring-brand"
          />
        </div>
        {msg ? (
          <p className={`rounded-lg px-3 py-2 text-sm ${msg.ok ? "bg-green-50 text-green-800" : "bg-red-50 text-red-700"}`}>
            {msg.text}
          </p>
        ) : null}
        <Button type="submit" disabled={saving} variant="secondary">
          {saving ? "Saving…" : "Save profile"}
        </Button>
      </form>
    </Card>
  );
}

// ---------------------------------------------------------------------------
// Password change section
// ---------------------------------------------------------------------------
function PasswordSection() {
  const [current, setCurrent] = useState("");
  const [next, setNext] = useState("");
  const [confirm, setConfirm] = useState("");
  const [saving, setSaving] = useState(false);
  const [msg, setMsg] = useState<{ ok: boolean; text: string } | null>(null);

  async function save(e: React.FormEvent) {
    e.preventDefault();
    if (next !== confirm) {
      setMsg({ ok: false, text: "New passwords do not match." });
      return;
    }
    setSaving(true);
    setMsg(null);
    try {
      await authApi.changePassword(current, next);
      setCurrent(""); setNext(""); setConfirm("");
      setMsg({ ok: true, text: "Password changed. You may need to sign in again on other devices." });
    } catch (err) {
      setMsg({ ok: false, text: err instanceof ApiError ? err.message : "Failed to change password." });
    } finally {
      setSaving(false);
    }
  }

  return (
    <Card>
      <CardTitle>Change password</CardTitle>
      <form onSubmit={save} className="space-y-4 mt-3">
        <div>
          <label htmlFor="current_pw" className="mb-1 block text-sm font-medium text-slate-700">
            Current password
          </label>
          <input
            id="current_pw"
            type="password"
            autoComplete="current-password"
            required
            value={current}
            onChange={(e) => setCurrent(e.target.value)}
            className="w-full rounded-lg border border-slate-300 px-3 py-2 text-sm focus:border-brand focus:outline-none focus:ring-1 focus:ring-brand"
          />
        </div>
        <div>
          <label htmlFor="new_pw" className="mb-1 block text-sm font-medium text-slate-700">
            New password
          </label>
          <input
            id="new_pw"
            type="password"
            autoComplete="new-password"
            required
            minLength={12}
            value={next}
            onChange={(e) => setNext(e.target.value)}
            className="w-full rounded-lg border border-slate-300 px-3 py-2 text-sm focus:border-brand focus:outline-none focus:ring-1 focus:ring-brand"
          />
          <p className="mt-1 text-xs text-slate-400">Min 12 characters, uppercase, lowercase, and a number.</p>
        </div>
        <div>
          <label htmlFor="confirm_pw" className="mb-1 block text-sm font-medium text-slate-700">
            Confirm new password
          </label>
          <input
            id="confirm_pw"
            type="password"
            autoComplete="new-password"
            required
            value={confirm}
            onChange={(e) => setConfirm(e.target.value)}
            className="w-full rounded-lg border border-slate-300 px-3 py-2 text-sm focus:border-brand focus:outline-none focus:ring-1 focus:ring-brand"
          />
        </div>
        {msg ? (
          <p className={`rounded-lg px-3 py-2 text-sm ${msg.ok ? "bg-green-50 text-green-800" : "bg-red-50 text-red-700"}`}>
            {msg.text}
          </p>
        ) : null}
        <Button type="submit" disabled={saving} variant="secondary">
          {saving ? "Saving…" : "Change password"}
        </Button>
      </form>
    </Card>
  );
}

// ---------------------------------------------------------------------------
// 2FA section
// ---------------------------------------------------------------------------
type TwoFAStep = "idle" | "setup" | "codes";

function TwoFASection() {
  const { user, refreshUser } = useAuth();
  const enabled = user?.totp_enabled ?? false;

  const [step, setStep] = useState<TwoFAStep>("idle");
  const [otpauthUri, setOtpauthUri] = useState("");
  const [secret, setSecret] = useState("");
  const [code, setCode] = useState("");
  const [recoveryCodes, setRecoveryCodes] = useState<string[]>([]);
  const [disablePw, setDisablePw] = useState("");
  const [disableCode, setDisableCode] = useState("");
  const [working, setWorking] = useState(false);
  const [msg, setMsg] = useState<{ ok: boolean; text: string } | null>(null);

  async function startSetup() {
    setWorking(true); setMsg(null);
    try {
      const data = await apiFetch<{ secret: string; otpauth_uri: string }>("/auth/2fa/setup", {
        method: "POST",
      });
      setSecret(data.secret);
      setOtpauthUri(data.otpauth_uri);
      setStep("setup");
    } catch (err) {
      setMsg({ ok: false, text: err instanceof ApiError ? err.message : "Failed to start 2FA setup." });
    } finally {
      setWorking(false);
    }
  }

  async function confirmSetup(e: React.FormEvent) {
    e.preventDefault();
    setWorking(true); setMsg(null);
    try {
      const data = await apiFetch<{ recovery_codes: string[] }>("/auth/2fa/verify", {
        method: "POST",
        body: JSON.stringify({ code }),
      });
      setRecoveryCodes(data.recovery_codes);
      setStep("codes");
      await refreshUser();
    } catch (err) {
      setMsg({ ok: false, text: err instanceof ApiError ? err.message : "Invalid code. Try again." });
    } finally {
      setWorking(false);
    }
  }

  async function disable(e: React.FormEvent) {
    e.preventDefault();
    setWorking(true); setMsg(null);
    try {
      await apiFetch("/auth/2fa/disable", {
        method: "POST",
        body: JSON.stringify({ password: disablePw, code: disableCode }),
      });
      setDisablePw(""); setDisableCode("");
      setMsg({ ok: true, text: "Two-factor authentication disabled." });
      await refreshUser();
    } catch (err) {
      setMsg({ ok: false, text: err instanceof ApiError ? err.message : "Failed to disable 2FA." });
    } finally {
      setWorking(false);
    }
  }

  if (step === "codes") {
    return (
      <Card>
        <CardTitle>Two-factor authentication — enabled</CardTitle>
        <p className="mt-3 text-sm text-green-800 bg-green-50 rounded-lg px-3 py-2">
          2FA is now active. Save these recovery codes somewhere safe — they are shown only once.
        </p>
        <ul className="mt-3 grid grid-cols-2 gap-1">
          {recoveryCodes.map((c) => (
            <li key={c} className="rounded bg-slate-100 px-2 py-1 font-mono text-xs text-slate-700">{c}</li>
          ))}
        </ul>
        <Button className="mt-4" variant="secondary" onClick={() => setStep("idle")}>Done</Button>
      </Card>
    );
  }

  if (!enabled) {
    return (
      <Card>
        <CardTitle>Two-factor authentication</CardTitle>
        <p className="mt-2 text-sm text-slate-500">
          Add an extra layer of security with an authenticator app (Google Authenticator, Authy, etc.).
        </p>
        {step === "setup" ? (
          <div className="mt-4 space-y-4">
            <p className="text-sm text-slate-600">
              Scan this code with your authenticator app, or enter the key manually.
            </p>
            {/* Simple text fallback — QR library can be added later */}
            <div className="rounded-lg border border-slate-200 bg-slate-50 px-3 py-3">
              <p className="text-xs text-slate-500 mb-1">Manual entry key:</p>
              <p className="font-mono text-sm text-slate-800 break-all">{secret}</p>
              <p className="mt-2 text-xs text-slate-400 break-all">URI: {otpauthUri}</p>
            </div>
            <form onSubmit={confirmSetup} className="space-y-3">
              <div>
                <label className="mb-1 block text-sm font-medium text-slate-700">
                  Enter the 6-digit code from your app
                </label>
                <input
                  type="text"
                  inputMode="numeric"
                  pattern="[0-9]{6}"
                  maxLength={6}
                  required
                  value={code}
                  onChange={(e) => setCode(e.target.value)}
                  className="w-32 rounded-lg border border-slate-300 px-3 py-2 text-sm font-mono focus:border-brand focus:outline-none focus:ring-1 focus:ring-brand"
                />
              </div>
              {msg ? <p className="text-sm text-red-700">{msg.text}</p> : null}
              <div className="flex gap-2">
                <Button type="submit" disabled={working}>{working ? "Verifying…" : "Activate 2FA"}</Button>
                <Button type="button" variant="secondary" onClick={() => setStep("idle")}>Cancel</Button>
              </div>
            </form>
          </div>
        ) : (
          <>
            {msg ? <p className="mt-2 text-sm text-red-700">{msg.text}</p> : null}
            <Button className="mt-4" onClick={startSetup} disabled={working} variant="secondary">
              {working ? "Starting…" : "Enable 2FA"}
            </Button>
          </>
        )}
      </Card>
    );
  }

  return (
    <Card>
      <CardTitle>Two-factor authentication</CardTitle>
      <p className="mt-2 text-sm text-green-700 bg-green-50 rounded px-2 py-1 inline-block">Active</p>
      <p className="mt-3 text-sm text-slate-500">
        To disable, confirm your password and enter a code from your authenticator app.
      </p>
      <form onSubmit={disable} className="mt-4 space-y-3">
        <div>
          <label className="mb-1 block text-sm font-medium text-slate-700">Password</label>
          <input
            type="password"
            autoComplete="current-password"
            required
            value={disablePw}
            onChange={(e) => setDisablePw(e.target.value)}
            className="w-full rounded-lg border border-slate-300 px-3 py-2 text-sm focus:border-brand focus:outline-none focus:ring-1 focus:ring-brand"
          />
        </div>
        <div>
          <label className="mb-1 block text-sm font-medium text-slate-700">Authenticator code</label>
          <input
            type="text"
            inputMode="numeric"
            pattern="[0-9]{6}"
            maxLength={6}
            required
            value={disableCode}
            onChange={(e) => setDisableCode(e.target.value)}
            className="w-32 rounded-lg border border-slate-300 px-3 py-2 text-sm font-mono focus:border-brand focus:outline-none focus:ring-1 focus:ring-brand"
          />
        </div>
        {msg ? (
          <p className={`text-sm ${msg.ok ? "text-green-800" : "text-red-700"}`}>{msg.text}</p>
        ) : null}
        <Button type="submit" disabled={working} variant="secondary">
          {working ? "Disabling…" : "Disable 2FA"}
        </Button>
      </form>
    </Card>
  );
}

// ---------------------------------------------------------------------------
// Billing section
// ---------------------------------------------------------------------------
const PLAN_LABELS: Record<string, string> = {
  trial: "Trial",
  pro: "Pro",
  agency: "Agency",
  enterprise: "Enterprise",
};

const STATUS_LABELS: Record<string, { label: string; color: string }> = {
  trialing:   { label: "Trial",    color: "bg-blue-100 text-blue-800"  },
  active:     { label: "Active",   color: "bg-green-100 text-green-800" },
  past_due:   { label: "Past due", color: "bg-amber-100 text-amber-800" },
  canceled:   { label: "Canceled", color: "bg-slate-100 text-slate-600" },
  incomplete: { label: "Pending",  color: "bg-slate-100 text-slate-600" },
};

function fmt(cents: number) {
  return `$${(cents / 100).toFixed(0)}`;
}

function daysLeft(iso: string | null) {
  if (!iso) return null;
  const diff = new Date(iso).getTime() - Date.now();
  return Math.max(0, Math.ceil(diff / 86400000));
}

function BillingSection() {
  const [bs, setBs] = useState<BillingStatus | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [plan, setPlan] = useState<"pro" | "agency">("pro");
  const [billingInterval, setBillingInterval] = useState<"monthly" | "annual">("monthly");
  const [working, setWorking] = useState(false);

  useEffect(() => {
    billingApi.status()
      .then(setBs)
      .catch((e) => setError(e instanceof ApiError ? e.message : "Failed to load billing info."))
      .finally(() => setLoading(false));
  }, []);

  async function goCheckout() {
    setWorking(true);
    try {
      const { checkout_url } = await billingApi.checkout(plan, billingInterval);
      window.location.href = checkout_url;
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Could not start checkout.");
      setWorking(false);
    }
  }

  async function goPortal() {
    setWorking(true);
    try {
      const { portal_url } = await billingApi.portal();
      window.location.href = portal_url;
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Could not open billing portal.");
      setWorking(false);
    }
  }

  if (loading) {
    return (
      <Card>
        <CardTitle>Subscription</CardTitle>
        <p className="mt-2 text-sm text-slate-400">Loading…</p>
      </Card>
    );
  }

  const statusMeta = bs?.status ? (STATUS_LABELS[bs.status] ?? { label: bs.status, color: "bg-slate-100 text-slate-600" }) : null;
  const days = daysLeft(bs?.trial_ends_at ?? null);
  const isPaid = bs?.status === "active" || bs?.status === "past_due";
  const isExpired = bs?.is_trial_expired;

  // Compute display price based on selected plan/interval
  const displayPrice = bs ? {
    pro_monthly:    bs.prices.pro_monthly_cents,
    pro_annual:     bs.prices.pro_annual_cents,
    agency_monthly: bs.prices.agency_monthly_cents,
    agency_annual:  bs.prices.agency_annual_cents,
  } : null;

  const selectedCents = displayPrice
    ? displayPrice[`${plan}_${billingInterval}` as keyof typeof displayPrice]
    : null;

  return (
    <Card className="lg:col-span-2">
      <div className="flex items-start justify-between">
        <CardTitle>Subscription</CardTitle>
        {statusMeta && (
          <span className={`rounded-full px-2.5 py-0.5 text-xs font-medium ${statusMeta.color}`}>
            {statusMeta.label}
          </span>
        )}
      </div>

      {error && (
        <p className="mt-2 rounded-lg bg-red-50 px-3 py-2 text-sm text-red-700">{error}</p>
      )}

      {bs && (
        <div className="mt-3 space-y-1 text-sm text-slate-600">
          <p>
            <span className="font-medium">Current plan:</span>{" "}
            {PLAN_LABELS[bs.plan] ?? bs.plan}
            {bs.billing_interval ? ` · billed ${bs.billing_interval}` : ""}
          </p>
          {bs.status === "trialing" && days !== null && (
            <p className={days <= 3 ? "font-medium text-amber-700" : ""}>
              {isExpired
                ? "Your trial has expired — upgrade to restore access."
                : `Trial ends in ${days} day${days === 1 ? "" : "s"}.`}
            </p>
          )}
          {bs.current_period_end && isPaid && (
            <p className="text-slate-500 text-xs">
              Next renewal: {new Date(bs.current_period_end).toLocaleDateString()}
            </p>
          )}
        </div>
      )}

      {/* Manage billing for paid subscribers */}
      {isPaid && (
        <div className="mt-4">
          <Button variant="secondary" onClick={goPortal} disabled={working}>
            {working ? "Opening…" : "Manage billing & invoices"}
          </Button>
          <p className="mt-1 text-xs text-slate-400">
            Change plan, update payment method, or cancel via Stripe.
          </p>
        </div>
      )}

      {/* Upgrade UI for trial / expired users */}
      {!isPaid && (
        <div className="mt-4 space-y-3">
          <p className="text-sm font-medium text-slate-700">Upgrade your plan</p>

          <div className="flex gap-3">
            {(["pro", "agency"] as const).map((p) => (
              <button
                key={p}
                type="button"
                onClick={() => setPlan(p)}
                className={`flex-1 rounded-lg border px-4 py-3 text-left text-sm transition-colors ${
                  plan === p
                    ? "border-brand bg-brand/5 text-brand"
                    : "border-slate-200 hover:border-slate-300"
                }`}
              >
                <p className="font-semibold">{PLAN_LABELS[p]}</p>
                {displayPrice && (
                  <p className="text-xs text-slate-500 mt-0.5">
                    {fmt(displayPrice[`${p}_monthly`])}/mo or {fmt(displayPrice[`${p}_annual`])}/yr
                  </p>
                )}
                {p === "pro" && (
                  <p className="mt-1 text-xs text-slate-500">3 seats · 10k contacts · 5 social connections</p>
                )}
                {p === "agency" && (
                  <p className="mt-1 text-xs text-slate-500">15 seats · 100k contacts · unlimited brands</p>
                )}
              </button>
            ))}
          </div>

          <div className="flex items-center gap-3">
            <span className="text-sm text-slate-600">Billing:</span>
            {(["monthly", "annual"] as const).map((iv) => (
              <button
                key={iv}
                type="button"
                onClick={() => setBillingInterval(iv)}
                className={`rounded-full px-3 py-1 text-xs font-medium transition-colors ${
                  billingInterval === iv
                    ? "bg-brand text-white"
                    : "bg-slate-100 text-slate-600 hover:bg-slate-200"
                }`}
              >
                {iv === "annual" ? "Annual (save 20%)" : "Monthly"}
              </button>
            ))}
          </div>

          {selectedCents && (
            <p className="text-sm text-slate-700">
              <span className="text-xl font-bold text-slate-900">
                {billingInterval === "annual"
                  ? `${fmt(selectedCents)}/yr`
                  : `${fmt(selectedCents)}/mo`}
              </span>
              {billingInterval === "annual" && (
                <span className="ml-2 text-xs text-slate-500">
                  (~{fmt(Math.round(selectedCents / 12))}/mo)
                </span>
              )}
            </p>
          )}

          <Button onClick={goCheckout} disabled={working}>
            {working ? "Opening checkout…" : `Upgrade to ${PLAN_LABELS[plan]}`}
          </Button>
        </div>
      )}
    </Card>
  );
}

// ---------------------------------------------------------------------------
// Page
// ---------------------------------------------------------------------------
export default function ProfilePage() {
  return (
    <>
      <PageHeader
        title="Profile & Security"
        description="Update your name, password, two-factor authentication, and subscription."
      />
      <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
        <BillingSection />
        <ProfileSection />
        <PasswordSection />
        <TwoFASection />
      </div>
    </>
  );
}
