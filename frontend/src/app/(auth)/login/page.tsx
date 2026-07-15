"use client";

import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { Suspense, useState } from "react";

import { Button } from "@/components/ui/Button";
import { ApiError, authApi } from "@/lib/api";

function LoginForm() {
  const router = useRouter();
  const params = useSearchParams();
  const next = params.get("next") || "/dashboard";
  const justReset = params.get("reset") === "1";

  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);
  // Email-code (anti-bot) second step.
  const [otp, setOtp] = useState<{ pending: string; maskedEmail: string } | null>(null);
  const [code, setCode] = useState("");

  async function onSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    setSubmitting(true);
    try {
      const res = await authApi.login(email, password);
      if ("email_otp_required" in res) {
        setOtp({ pending: res.pending_token, maskedEmail: res.email });
      } else if ("twofa_required" in res) {
        setError("This account uses an authenticator app. 2FA sign-in isn't available here yet.");
      } else {
        router.replace(next);
      }
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Unable to sign in. Try again.");
    } finally {
      setSubmitting(false);
    }
  }

  async function submitCode(e: React.FormEvent) {
    e.preventDefault();
    if (!otp) return;
    setError(null);
    setSubmitting(true);
    try {
      await authApi.emailOtpLogin(otp.pending, code.trim());
      router.replace(next);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Invalid code. Try again.");
    } finally {
      setSubmitting(false);
    }
  }

  if (otp) {
    return (
      <div className="flex min-h-screen items-center justify-center bg-slate-50 px-4">
        <div className="w-full max-w-sm rounded-2xl border border-slate-200 bg-white p-8 shadow-sm">
          <div className="mb-6 text-center">
            <img src="/logo.svg" alt="RevOS360" width={160} height={36} className="mx-auto" />
            <p className="mt-3 text-sm text-slate-500">
              Enter the code we emailed to <span className="font-medium">{otp.maskedEmail}</span>
            </p>
          </div>
          <form onSubmit={submitCode} className="space-y-4">
            <input
              inputMode="numeric" autoComplete="one-time-code" autoFocus required
              value={code} onChange={(e) => setCode(e.target.value)}
              placeholder="6-digit code"
              className="w-full rounded-lg border border-slate-300 px-3 py-2 text-center text-lg tracking-widest focus:border-brand focus:outline-none focus:ring-1 focus:ring-brand"
            />
            {error ? <p className="rounded-lg bg-red-50 px-3 py-2 text-sm text-red-700">{error}</p> : null}
            <Button type="submit" disabled={submitting} className="w-full">
              {submitting ? "Verifying…" : "Verify & sign in"}
            </Button>
          </form>
          <button
            onClick={() => { setOtp(null); setCode(""); setError(null); }}
            className="mt-4 w-full text-center text-xs text-slate-400 hover:text-slate-600"
          >
            ← Back to sign in
          </button>
        </div>
      </div>
    );
  }

  return (
    <div className="flex min-h-screen items-center justify-center bg-slate-50 px-4">
      <div className="w-full max-w-sm rounded-2xl border border-slate-200 bg-white p-8 shadow-sm">
        <div className="mb-6 text-center">
          <img src="/logo.svg" alt="RevOS360" width={160} height={36} className="mx-auto" />
          <p className="mt-3 text-sm text-slate-500">Sign in to your admin console</p>
        </div>
        {justReset ? (
          <p className="mb-4 rounded-lg bg-green-50 px-3 py-2 text-sm text-green-800">
            Password updated — sign in with your new password.
          </p>
        ) : null}
        <form onSubmit={onSubmit} className="space-y-4">
          <div>
            <label htmlFor="email" className="mb-1 block text-sm font-medium text-slate-700">
              Email
            </label>
            <input
              id="email"
              type="email"
              autoComplete="username"
              required
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              className="w-full rounded-lg border border-slate-300 px-3 py-2 text-sm focus:border-brand focus:outline-none focus:ring-1 focus:ring-brand"
            />
          </div>
          <div>
            <label htmlFor="password" className="mb-1 block text-sm font-medium text-slate-700">
              Password
            </label>
            <input
              id="password"
              type="password"
              autoComplete="current-password"
              required
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              className="w-full rounded-lg border border-slate-300 px-3 py-2 text-sm focus:border-brand focus:outline-none focus:ring-1 focus:ring-brand"
            />
            <div className="mt-1 text-right">
              <Link href="/forgot-password" className="text-xs text-slate-500 hover:text-brand hover:underline">
                Forgot password?
              </Link>
            </div>
          </div>
          {error ? (
            <p className="rounded-lg bg-red-50 px-3 py-2 text-sm text-red-700">{error}</p>
          ) : null}
          <Button type="submit" disabled={submitting} className="w-full">
            {submitting ? "Signing in…" : "Sign in"}
          </Button>
        </form>
        <p className="mt-6 text-center text-sm text-slate-500">
          Don&apos;t have an account?{" "}
          <Link href="/register" className="font-medium text-brand hover:underline">
            Create one free
          </Link>
        </p>
        <p className="mt-4 text-center text-xs text-slate-400">
          <Link href="/privacy" className="hover:underline">Privacy Policy</Link>
          {" · "}
          <Link href="/terms" className="hover:underline">Terms of Service</Link>
        </p>
      </div>
    </div>
  );
}

export default function LoginPage() {
  return (
    <Suspense fallback={null}>
      <LoginForm />
    </Suspense>
  );
}
