"use client";

// Brand-first onboarding: shown when the account has zero brands, because
// nearly everything in the system inherits from one. Dismissible (per
// session) so exploration isn't blocked — brand-dependent pages re-surface
// the same creation flow through their empty states.

import { useEffect, useState } from "react";

import { BrandCreateForm } from "@/components/BrandCreateForm";
import { apiFetch } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { useBrand } from "@/lib/brand";

const DISMISS_KEY = "revos.onboardingDismissed"; // sessionStorage: re-surfaces next session

function recordEvent(event: string) {
  // Fire-and-forget telemetry — never block or break onboarding over it.
  apiFetch<void>(`/analytics/ui-events?event=${encodeURIComponent(event)}`, { method: "POST" })
    .catch(() => undefined);
}

export function BrandOnboarding() {
  const { user } = useAuth();
  const { brands, loading, refresh } = useBrand();
  const [dismissed, setDismissed] = useState(true); // assume dismissed until hydrated
  const [shown, setShown] = useState(false);

  const canCreate = user?.role === "admin" || user?.role === "owner";

  useEffect(() => {
    setDismissed(window.sessionStorage.getItem(DISMISS_KEY) === "1");
  }, []);

  const visible = !loading && brands.length === 0 && !dismissed && canCreate;

  useEffect(() => {
    if (visible && !shown) {
      setShown(true);
      recordEvent("onboarding_shown");
    }
  }, [visible, shown]);

  if (!visible) return null;

  function dismiss() {
    try {
      window.sessionStorage.setItem(DISMISS_KEY, "1");
    } catch {
      /* private mode */
    }
    setDismissed(true);
    recordEvent("onboarding_dismissed");
  }

  return (
    <div className="fixed inset-0 z-[60] flex items-center justify-center bg-slate-900/40 p-4">
      <div className="w-full max-w-2xl rounded-2xl border border-slate-200 bg-white p-8 shadow-xl">
        <h1 className="text-2xl font-bold text-slate-900">
          Everything in this system inherits from a brand.
        </h1>
        <p className="mt-1 text-lg text-slate-600">Create your first one.</p>
        <p className="mt-3 text-sm text-slate-500">
          Your brand is the source of truth every email, post, campaign, and approval draws
          from — name it, and the rest of the product unlocks around it. You can refine voice,
          claims, and guardrails in the Brand Book afterwards.
        </p>

        <div className="mt-6">
          <BrandCreateForm
            submitLabel="Create my first brand"
            onCreated={async () => {
              recordEvent("onboarding_completed");
              await refresh();
            }}
          />
        </div>

        <button
          type="button"
          onClick={dismiss}
          className="mt-4 text-sm text-slate-400 underline-offset-2 hover:text-slate-600 hover:underline"
        >
          Not now — let me look around first
        </button>
      </div>
    </div>
  );
}
