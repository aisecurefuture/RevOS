"use client";

import { useEffect, useState } from "react";

import { PageHeader } from "@/components/PageHeader";
import { Button } from "@/components/ui/Button";
import { Card, CardTitle } from "@/components/ui/Card";
import { ApiError, apiFetch, authApi } from "@/lib/api";
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
// Page
// ---------------------------------------------------------------------------
export default function ProfilePage() {
  return (
    <>
      <PageHeader
        title="Profile & Security"
        description="Update your name, password, and two-factor authentication."
      />
      <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
        <ProfileSection />
        <PasswordSection />
        <TwoFASection />
      </div>
    </>
  );
}
