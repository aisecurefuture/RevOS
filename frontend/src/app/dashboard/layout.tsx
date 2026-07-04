"use client";

import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import type { ReactNode } from "react";

import { Sidebar } from "@/components/Sidebar";
import { Topbar } from "@/components/Topbar";
import { Spinner } from "@/components/ui/Spinner";
import { billingApi, type BillingStatus } from "@/lib/api";
import { AuthProvider, useAuth } from "@/lib/auth";
import { BrandProvider } from "@/lib/brand";

function Shell({ children }: { children: ReactNode }) {
  const { user, loading } = useAuth();
  const router = useRouter();
  const [billing, setBilling] = useState<BillingStatus | null>(null);
  const [billingLoading, setBillingLoading] = useState(true);

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
    <div className="flex h-screen overflow-hidden">
      <Sidebar />
      <div className="flex flex-1 flex-col overflow-hidden">
        <Topbar />
        <main className="flex-1 overflow-y-auto p-6">{children}</main>
      </div>
    </div>
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
