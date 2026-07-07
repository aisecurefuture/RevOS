"use client";

import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { Suspense, useEffect, useState } from "react";

import { ApiError, authApi } from "@/lib/api";
import { AuthProvider, useAuth } from "@/lib/auth";

function Shell({ children }: { children: React.ReactNode }) {
  return (
    <div className="flex min-h-screen items-center justify-center bg-slate-50 px-4">
      <div className="w-full max-w-sm rounded-2xl border border-slate-200 bg-white p-8 text-center shadow-sm">
        <img src="/logo.svg" alt="RevOS360" width={160} height={36} className="mx-auto mb-6" />
        {children}
      </div>
    </div>
  );
}

function VerifyEmailForm() {
  const params = useSearchParams();
  const token = params.get("token") || "";
  const { user, loading, refreshUser } = useAuth();

  const [status, setStatus] = useState<"verifying" | "done" | "error">("verifying");
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (loading || !token) return;
    (async () => {
      try {
        await authApi.verifyEmail(token);
        // If there's an active session, refresh the cached user so any
        // "verify your email" gating disappears immediately.
        if (user) await refreshUser();
        setStatus("done");
      } catch (err) {
        setStatus("error");
        setError(err instanceof ApiError ? err.message : "Could not verify this email address.");
      }
    })();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [loading, token]);

  if (!token) {
    return <p className="text-sm text-slate-500">This verification link is missing its token.</p>;
  }

  if (loading || status === "verifying") {
    return <p className="text-sm text-slate-500">Verifying your email…</p>;
  }

  if (status === "error") {
    return (
      <>
        <p className="text-sm text-red-600">{error}</p>
        <p className="mt-3 text-xs text-slate-400">
          Verification links expire after 72 hours. You can request a new one from your dashboard.
        </p>
      </>
    );
  }

  return (
    <>
      <p className="text-sm text-slate-600">✓ Your email address is verified.</p>
      <Link
        href={user ? "/dashboard" : "/login"}
        className="mt-4 inline-block w-full rounded-lg bg-brand px-4 py-2 text-sm font-medium text-white hover:opacity-90"
      >
        {user ? "Go to dashboard" : "Log in"}
      </Link>
    </>
  );
}

export default function VerifyEmailPage() {
  return (
    <AuthProvider>
      <Shell>
        <Suspense fallback={<p className="text-sm text-slate-500">Loading…</p>}>
          <VerifyEmailForm />
        </Suspense>
      </Shell>
    </AuthProvider>
  );
}
