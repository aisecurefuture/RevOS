"use client";

import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import type { ReactNode } from "react";

import { BrandOnboarding } from "@/components/BrandOnboarding";
import { Sidebar } from "@/components/Sidebar";
import { Topbar } from "@/components/Topbar";
import { Spinner } from "@/components/ui/Spinner";
import { authApi, billingApi, ApiError, type BillingStatus } from "@/lib/api";
import { AuthProvider, useAuth } from "@/lib/auth";
import { BrandProvider } from "@/lib/brand";
import { TourProvider } from "@/lib/tour";

function VerifyEmailBanner() {
  const [sent, setSent] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function resend() {
    setBusy(true);
    setError(null);
    try {
      await authApi.resendVerification();
      setSent(true);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not resend the email");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="flex flex-wrap items-center justify-between gap-2 border-b border-amber-200 bg-amber-50 px-6 py-2 text-sm text-amber-800">
      <span>
        Verify your email address to connect social accounts, invite teammates, or publish content.
      </span>
      <span className="flex items-center gap-2">
        {sent ? (
          <span className="text-xs text-amber-700">Verification email sent — check your inbox.</span>
        ) : (
          <button
            onClick={() => void resend()}
            disabled={busy}
            className="rounded-full bg-amber-100 px-3 py-1 text-xs font-medium text-amber-900 hover:bg-amber-200"
          >
            {busy ? "Sending…" : "Resend verification email"}
          </button>
        )}
        {error ? <span className="text-xs text-red-600">{error}</span> : null}
      </span>
    </div>
  );
}

function Shell({ children }: { children: ReactNode }) {
  const { user, loading } = useAuth();
  const router = useRouter();
  const [billing, setBilling] = useState<BillingStatus | null>(null);
  const [billingLoading, setBillingLoading] = useState(true);
  const [sidebarOpen, setSidebarOpen] = useState(false);

  useEffect(() => {
    if (!loading && !user) router.replace("/login");
  }, [loading, user, router]);

  useEffect(() => {
    if (!user) return;
    billingApi.status()
      .then((data) => {
        setBilling(data);
        // No subscription or expired trial → paywall
        if (data.status === null || data.is_trial_expired) {
          router.replace("/subscribe");
        }
      })
      .catch(() => {
        // If status check errors (e.g. 503 Stripe unconfigured), let them through.
        // The billing section on the profile page will surface the upgrade UI.
        setBillingLoading(false);
      })
      .finally(() => setBillingLoading(false));
  }, [user, router]);

  if (loading || billingLoading) {
    return (
      <div className="flex h-screen items-center justify-center">
        <Spinner label="Loading your console…" />
      </div>
    );
  }
  if (!user) return null;
  // If billing loaded and access is blocked, render nothing while redirect fires
  if (billing && (billing.status === null || billing.is_trial_expired)) return null;

  return (
    <TourProvider>
      <div className="flex h-screen overflow-hidden">
        <Sidebar open={sidebarOpen} onClose={() => setSidebarOpen(false)} />
        <div className="flex flex-1 flex-col overflow-hidden">
          <Topbar onMenuClick={() => setSidebarOpen(true)} />
          {!user.email_verified ? <VerifyEmailBanner /> : null}
          <main className="flex-1 overflow-y-auto p-4 sm:p-6">{children}</main>
        </div>
        <BrandOnboarding />
      </div>
    </TourProvider>
  );
}

export default function DashboardLayout({ children }: { children: ReactNode }) {
  return (
    <AuthProvider>
      <BrandProvider>
        <Shell>{children}</Shell>
      </BrandProvider>
    </AuthProvider>
  );
}
