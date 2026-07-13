"use client";

// Empty states must never be dead ends: every brand-dependent page funnels
// into the same brand-creation flow (the shared form on /dashboard/brands).

import Link from "next/link";

export function NoBrandCta({ feature = "This page" }: { feature?: string }) {
  return (
    <div className="rounded-xl border border-brand/30 bg-brand/5 px-4 py-6 text-center">
      <p className="text-sm font-medium text-slate-700">
        {feature} inherits from a brand — create your first one to unlock it.
      </p>
      <Link
        href="/dashboard/brands"
        className="mt-3 inline-block rounded-lg bg-brand px-4 py-2 text-sm font-medium text-white hover:opacity-90"
      >
        Create a brand →
      </Link>
    </div>
  );
}
