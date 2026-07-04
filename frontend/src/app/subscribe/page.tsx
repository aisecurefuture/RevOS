"use client";

import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";

import { Button } from "@/components/ui/Button";
import { ApiError, billingApi, type BillingStatus } from "@/lib/api";

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function fmt(cents: number) {
  return `$${(cents / 100).toFixed(0)}`;
}

function daysLeft(iso: string | null) {
  if (!iso) return null;
  const diff = new Date(iso).getTime() - Date.now();
  return Math.max(0, Math.ceil(diff / 86400000));
}

// ---------------------------------------------------------------------------
// Plan card
// ---------------------------------------------------------------------------

interface PlanCardProps {
  name: "pro" | "agency";
  label: string;
  monthlyCents: number;
  annualCents: number;
  features: string[];
  interval: "monthly" | "annual";
  selected: boolean;
  onSelect: () => void;
}

function PlanCard({ name, label, monthlyCents, annualCents, features, interval, selected, onSelect }: PlanCardProps) {
  const displayCents = interval === "annual" ? annualCents : monthlyCents;
  const isAnnual = interval === "annual";

  return (
    <button
      type="button"
      onClick={onSelect}
      className={`w-full rounded-2xl border-2 p-6 text-left transition-all ${
        selected
          ? "border-brand bg-brand/5 shadow-md"
          : "border-slate-200 hover:border-slate-300 hover:shadow-sm"
      }`}
    >
      <div className="flex items-start justify-between">
        <div>
          <p className="text-lg font-bold text-slate-900">{label}</p>
          <p className="mt-1 text-3xl font-extrabold text-slate-900">
            {isAnnual ? `${fmt(annualCents)}/yr` : `${fmt(monthlyCents)}/mo`}
          </p>
          {isAnnual && (
            <p className="text-xs text-slate-500">
              ~{fmt(Math.round(annualCents / 12))}/mo · save {Math.round((1 - annualCents / (monthlyCents * 12)) * 100)}%
            </p>
          )}
        </div>
        <div className={`mt-1 h-5 w-5 rounded-full border-2 flex items-center justify-center ${
          selected ? "border-brand bg-brand" : "border-slate-300"
        }`}>
          {selected && <span className="block h-2 w-2 rounded-full bg-white" />}
        </div>
      </div>
      <ul className="mt-4 space-y-1.5">
        {features.map((f) => (
          <li key={f} className="flex items-center gap-2 text-sm text-slate-600">
            <span className="text-green-500">✓</span> {f}
          </li>
        ))}
      </ul>
      {name === "agency" && (
        <span className="mt-3 inline-block rounded-full bg-brand/10 px-2.5 py-0.5 text-xs font-medium text-brand">
          Most popular
        </span>
      )}
    </button>
  );
}

// ---------------------------------------------------------------------------
// Page
// ---------------------------------------------------------------------------

export default function SubscribePage() {
  const router = useRouter();

  const [bs, setBs] = useState<BillingStatus | null>(null);
  const [loading, setLoading] = useState(true);
  const [selectedPlan, setSelectedPlan] = useState<"trial" | "pro" | "agency">("trial");
  const [billingInterval, setBillingInterval] = useState<"monthly" | "annual">("monthly");
  const [working, setWorking] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    billingApi.status()
      .then((data) => {
        setBs(data);
        // If already on an active paid plan, skip this page
        if (data.status === "active" && data.plan !== "trial") {
          router.replace("/dashboard");
        }
        // If trial active (not expired), preselect trial
        if (data.status === "trialing" && !data.is_trial_expired) {
          setSelectedPlan("trial");
        }
        // Expired → force paid plan selection
        if (data.is_trial_expired) {
          setSelectedPlan("pro");
        }
      })
      .catch(() => {
        // No subscription yet — stay on page and offer trial
      })
      .finally(() => setLoading(false));
  }, [router]);

  async function handleContinue() {
    setWorking(true);
    setError(null);
    try {
      if (selectedPlan === "trial") {
        await billingApi.startTrial();
        router.replace("/dashboard");
      } else {
        const { checkout_url } = await billingApi.checkout(selectedPlan, billingInterval);
        window.location.href = checkout_url;
      }
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Something went wrong. Please try again.");
      setWorking(false);
    }
  }

  const days = daysLeft(bs?.trial_ends_at ?? null);
  const trialActive = bs?.status === "trialing" && !bs.is_trial_expired;
  const trialExpired = bs?.is_trial_expired ?? false;

  if (loading) {
    return (
      <div className="flex min-h-screen items-center justify-center bg-slate-50">
        <div className="text-slate-400 text-sm">Loading…</div>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-slate-50 px-4 py-16">
      <div className="mx-auto max-w-2xl">
        {/* Header */}
        <div className="mb-10 text-center">
          <img src="/logo.svg" alt="RevOS360" width={160} height={36} className="mx-auto mb-4" />
          <h1 className="text-3xl font-bold text-slate-900">
            {trialExpired ? "Your trial has ended" : "Choose your plan"}
          </h1>
          <p className="mt-2 text-slate-500">
            {trialExpired
              ? "Upgrade to keep access to your dashboard and all your data."
              : "Start with a 14-day free trial or go straight to a paid plan."}
          </p>
        </div>

        {/* Trial active banner */}
        {trialActive && days !== null && (
          <div className="mb-6 rounded-xl bg-blue-50 border border-blue-200 px-4 py-3 text-sm text-blue-800">
            Your free trial is active — <strong>{days} day{days === 1 ? "" : "s"}</strong> remaining.
            Continue to dashboard or upgrade any time.
          </div>
        )}

        {/* Trial expired banner */}
        {trialExpired && (
          <div className="mb-6 rounded-xl bg-amber-50 border border-amber-200 px-4 py-3 text-sm text-amber-800">
            Your 14-day trial has expired. Select a plan below to restore access.
          </div>
        )}

        {/* Billing interval toggle */}
        <div className="mb-6 flex items-center justify-center gap-2">
          {(["monthly", "annual"] as const).map((iv) => (
            <button
              key={iv}
              type="button"
              onClick={() => setBillingInterval(iv)}
              className={`rounded-full px-4 py-1.5 text-sm font-medium transition-colors ${
                billingInterval === iv
                  ? "bg-slate-900 text-white"
                  : "bg-white border border-slate-200 text-slate-600 hover:border-slate-300"
              }`}
            >
              {iv === "annual" ? "Annual (save ~20%)" : "Monthly"}
            </button>
          ))}
        </div>

        {/* Plan cards */}
        <div className="space-y-4">
          {/* Free trial option — only show if trial not expired */}
          {!trialExpired && (
            <button
              type="button"
              onClick={() => setSelectedPlan("trial")}
              className={`w-full rounded-2xl border-2 p-5 text-left transition-all ${
                selectedPlan === "trial"
                  ? "border-brand bg-brand/5 shadow-md"
                  : "border-slate-200 hover:border-slate-300 hover:shadow-sm"
              }`}
            >
              <div className="flex items-center justify-between">
                <div>
                  <p className="font-bold text-slate-900 text-lg">
                    {trialActive ? "Continue free trial" : "Start 14-day free trial"}
                  </p>
                  <p className="text-sm text-slate-500 mt-0.5">
                    {trialActive
                      ? `${days} day${days === 1 ? "" : "s"} remaining — no credit card required`
                      : "No credit card required · Full access · Cancel any time"}
                  </p>
                </div>
                <div className={`h-5 w-5 rounded-full border-2 flex items-center justify-center ${
                  selectedPlan === "trial" ? "border-brand bg-brand" : "border-slate-300"
                }`}>
                  {selectedPlan === "trial" && <span className="block h-2 w-2 rounded-full bg-white" />}
                </div>
              </div>
            </button>
          )}

          {bs && (
            <>
              <PlanCard
                name="pro"
                label="Pro"
                monthlyCents={bs.prices.pro_monthly_cents}
                annualCents={bs.prices.pro_annual_cents}
                features={["3 team seats", "10,000 contacts", "5 social connections", "50k emails/month", "AI drafts"]}
                interval={billingInterval}
                selected={selectedPlan === "pro"}
                onSelect={() => setSelectedPlan("pro")}
              />
              <PlanCard
                name="agency"
                label="Agency"
                monthlyCents={bs.prices.agency_monthly_cents}
                annualCents={bs.prices.agency_annual_cents}
                features={["15 team seats", "100,000 contacts", "Unlimited social connections", "Unlimited emails", "Client workspaces", "White-label", "API access"]}
                interval={billingInterval}
                selected={selectedPlan === "agency"}
                onSelect={() => setSelectedPlan("agency")}
              />
            </>
          )}

          {/* Fallback plan cards if billing status fetch failed */}
          {!bs && (
            <p className="text-center text-sm text-slate-500">
              Could not load pricing. Please refresh the page.
            </p>
          )}
        </div>

        {/* CTA */}
        {error && (
          <p className="mt-4 rounded-lg bg-red-50 px-3 py-2 text-sm text-red-700">{error}</p>
        )}

        <div className="mt-6">
          <Button
            onClick={handleContinue}
            disabled={working || !bs}
            className="w-full text-base py-3"
          >
            {working
              ? "Please wait…"
              : selectedPlan === "trial"
                ? trialActive ? "Continue to dashboard" : "Start free trial"
                : `Upgrade to ${selectedPlan === "pro" ? "Pro" : "Agency"}`}
          </Button>
        </div>

        <p className="mt-4 text-center text-xs text-slate-400">
          Payments secured by Stripe. Cancel any time.
        </p>
      </div>
    </div>
  );
}
