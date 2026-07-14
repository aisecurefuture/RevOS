"use client";

// Industry-tailored "Recommended for you" panel on the dashboard overview.
// Reads the selected brand's industry and surfaces its most-useful features
// as quick links. Personalization only — it highlights, never hides; every
// feature stays reachable from the nav. Dismissible per brand.

import Link from "next/link";
import { useEffect, useState } from "react";

import { Card, CardTitle } from "@/components/ui/Card";
import { useBrand } from "@/lib/brand";
import { FEATURE_META, findIndustry, recommendedFeatures } from "@/lib/industries";

const DISMISS_KEY = "revos.recommendDismissed"; // JSON: { [brandId]: true }

function loadDismissed(): Record<string, boolean> {
  if (typeof window === "undefined") return {};
  try {
    return JSON.parse(window.localStorage.getItem(DISMISS_KEY) || "{}");
  } catch {
    return {};
  }
}

export function RecommendedForYou() {
  const { brands, selectedBrandId } = useBrand();
  const [dismissed, setDismissed] = useState<Record<string, boolean>>({});
  const [hydrated, setHydrated] = useState(false);

  useEffect(() => {
    setDismissed(loadDismissed());
    setHydrated(true);
  }, []);

  // Resolve the brand whose recommendations to show: the selected one, or the
  // only brand if "All brands" is active and there's exactly one.
  const brand =
    brands.find((b) => b.id === selectedBrandId) ?? (brands.length === 1 ? brands[0] : null);

  if (!hydrated || !brand?.industry || dismissed[brand.id]) return null;

  const industry = findIndustry(brand.industry);
  const features = recommendedFeatures(brand.industry)
    .map((href) => ({ href, ...FEATURE_META[href] }))
    .filter((f) => f.label); // guard against any unmapped href

  if (features.length === 0) return null;

  const who = industry ? industry.label.toLowerCase() : brand.name;

  function dismiss() {
    const next = { ...dismissed, [brand!.id]: true };
    setDismissed(next);
    try {
      window.localStorage.setItem(DISMISS_KEY, JSON.stringify(next));
    } catch {
      /* private mode — just won't persist */
    }
  }

  return (
    <Card className="mb-4 border-brand/30 bg-brand/[0.03]" data-tour="recommended">
      <div className="mb-3 flex items-start justify-between gap-3">
        <div>
          <CardTitle>Recommended for you</CardTitle>
          <p className="text-xs text-slate-500">
            A quick-start path for {who}. You can use everything else anytime from the sidebar.
          </p>
        </div>
        <button
          onClick={dismiss}
          className="shrink-0 text-xs text-slate-400 hover:text-slate-600"
          aria-label="Dismiss recommendations"
        >
          Dismiss
        </button>
      </div>
      <div className="grid grid-cols-1 gap-2 sm:grid-cols-2 lg:grid-cols-3">
        {features.map((f, i) => (
          <Link
            key={f.href}
            href={f.href}
            className="flex items-start gap-3 rounded-lg border border-slate-200 bg-white p-3 transition-colors hover:border-brand/50 hover:bg-brand/[0.04]"
          >
            <span aria-hidden className="text-lg">{f.icon}</span>
            <span className="min-w-0">
              <span className="flex items-center gap-1.5 text-sm font-medium text-slate-800">
                {i === 0 ? (
                  <span className="rounded-full bg-brand/10 px-1.5 py-0.5 text-[10px] font-semibold uppercase tracking-wide text-brand">
                    Start here
                  </span>
                ) : null}
                {f.label}
              </span>
              <span className="mt-0.5 block text-xs text-slate-500">{f.blurb}</span>
            </span>
          </Link>
        ))}
      </div>
    </Card>
  );
}
