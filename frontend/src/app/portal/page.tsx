"use client";

import { useCallback, useEffect, useState } from "react";

import { ApiError } from "@/lib/api";
import { marketplaceApi } from "@/lib/resources";
import type { MatchCreator } from "@/lib/types";

import { ClaimForm } from "./ClaimForm";
import { CreatorPortalDashboard } from "./CreatorPortalDashboard";

export default function PortalHome() {
  const [creators, setCreators] = useState<MatchCreator[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [selectedId, setSelectedId] = useState<string | null>(null);

  const load = useCallback(async () => {
    try {
      const mine = await marketplaceApi.myClaimedCreators();
      setCreators(mine);
      setSelectedId((prev) => prev ?? mine[0]?.id ?? null);
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Failed to load your portal");
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  if (error) {
    return <div className="rounded-xl border border-red-500/30 bg-red-500/10 px-4 py-3 text-red-200">{error}</div>;
  }

  if (creators === null) {
    return <div className="animate-pulse text-white/40">Loading…</div>;
  }

  if (creators.length === 0) {
    return <ClaimForm onClaimed={load} />;
  }

  const selected = creators.find((c) => c.id === selectedId) ?? creators[0];

  return (
    <div className="space-y-6">
      {creators.length > 1 ? (
        <div className="flex flex-wrap gap-2">
          {creators.map((c) => (
            <button
              key={c.id}
              type="button"
              onClick={() => setSelectedId(c.id)}
              className={`rounded-full px-4 py-1.5 text-sm font-medium transition ${
                c.id === selected.id
                  ? "bg-white text-[#0b0713]"
                  : "border border-white/15 text-white/70 hover:border-white/30 hover:text-white"
              }`}
            >
              {c.display_name}
            </button>
          ))}
        </div>
      ) : null}
      <CreatorPortalDashboard creator={selected} />
    </div>
  );
}
