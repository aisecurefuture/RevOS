"use client";

import { useCallback, useEffect, useState } from "react";

import { ApiError } from "@/lib/api";
import { marketplaceApi } from "@/lib/resources";
import type { CollaborationRequest, Insights, MatchCreator } from "@/lib/types";

import { PublicPagePanel } from "./PublicPagePanel";

function scoreGlow(v: number): string {
  if (v >= 75) return "from-emerald-400 to-teal-400";
  if (v >= 55) return "from-sky-400 to-violet-400";
  if (v >= 35) return "from-amber-400 to-orange-400";
  return "from-white/30 to-white/10";
}

function ScoreDial({ overall, coverage }: { overall: number; coverage: number }) {
  const pct = Math.max(0, Math.min(100, overall));
  return (
    <div className="relative flex h-36 w-36 shrink-0 items-center justify-center">
      <div
        className="absolute inset-0 rounded-full"
        style={{
          background: `conic-gradient(rgb(168 85 247) ${pct * 3.6}deg, rgba(255,255,255,0.08) 0deg)`,
        }}
      />
      <div className="absolute inset-[6px] rounded-full bg-[#0b0713]" />
      <div className="relative text-center">
        <div className="text-3xl font-bold">{Math.round(overall)}</div>
        <div className="text-[10px] uppercase tracking-wide text-white/40">
          {Math.round(coverage * 100)}% verified
        </div>
      </div>
    </div>
  );
}

function StatChip({ label, value, hint }: { label: string; value: string; hint?: string }) {
  return (
    <div className="rounded-xl border border-white/10 bg-white/5 px-4 py-3">
      <div className="text-2xl font-bold tracking-tight">{value}</div>
      <div className="text-xs text-white/50">{label}</div>
      {hint ? <div className="mt-0.5 text-[11px] text-emerald-300">{hint}</div> : null}
    </div>
  );
}

const PRIORITY_GLOW: Record<string, string> = {
  high: "border-fuchsia-400/40 bg-fuchsia-500/10",
  medium: "border-violet-400/30 bg-violet-500/10",
  low: "border-white/10 bg-white/5",
};

const PRIORITY_BADGE: Record<string, string> = {
  high: "🔥 Do this now",
  medium: "⚡ Worth doing",
  low: "✨ Nice to have",
};

function pct(v: number | null | undefined): string {
  return v == null ? "—" : `${Math.round(v * 100)}%`;
}

export function CreatorPortalDashboard({ creator }: { creator: MatchCreator }) {
  const [insights, setInsights] = useState<Insights | null>(null);
  const [requests, setRequests] = useState<CollaborationRequest[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [busyId, setBusyId] = useState<string | null>(null);

  const load = useCallback(async () => {
    setError(null);
    try {
      const [ins, reqs] = await Promise.all([
        marketplaceApi.creatorInsights(creator.id),
        marketplaceApi.collaborations("incoming", "pending"),
      ]);
      setInsights(ins);
      setRequests(reqs.filter((r) => r.creator_id === creator.id));
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Failed to load your dashboard");
    }
  }, [creator.id]);

  useEffect(() => {
    void load();
  }, [load]);

  async function respond(id: string, accept: boolean) {
    setBusyId(id);
    try {
      await marketplaceApi.respond(id, accept);
      await load();
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Failed to respond");
    } finally {
      setBusyId(null);
    }
  }

  if (error) {
    return <div className="rounded-xl border border-red-500/30 bg-red-500/10 px-4 py-3 text-red-200">{error}</div>;
  }
  if (!insights) {
    return <div className="animate-pulse text-white/40">Loading your stats…</div>;
  }

  const { reputation, metrics, benchmarks, recommendations } = insights;

  return (
    <div className="space-y-6">
      {/* Hero */}
      <div className="rounded-2xl border border-white/10 bg-white/[0.03] p-6">
        <div className="flex flex-wrap items-center gap-6">
          <ScoreDial overall={reputation.overall} coverage={reputation.coverage} />
          <div className="min-w-[16rem] flex-1">
            <p className="text-xs uppercase tracking-wide text-white/40">Your reputation</p>
            <h1 className="text-2xl font-bold tracking-tight sm:text-3xl">{creator.display_name}</h1>
            <p className="mt-1 text-sm text-white/60">{reputation.rationale}</p>
            <div className={`mt-3 h-1.5 w-full max-w-xs overflow-hidden rounded-full bg-white/10`}>
              <div
                className={`h-full rounded-full bg-gradient-to-r ${scoreGlow(reputation.overall)}`}
                style={{ width: `${Math.max(4, reputation.overall)}%` }}
              />
            </div>
          </div>
        </div>
      </div>

      {/* Pending opportunities — the core loop */}
      <div>
        <h2 className="mb-3 flex items-center gap-2 text-lg font-semibold">
          Opportunities waiting for you
          {requests.length > 0 ? (
            <span className="rounded-full bg-fuchsia-500 px-2 py-0.5 text-xs font-bold">{requests.length}</span>
          ) : null}
        </h2>
        {requests.length === 0 ? (
          <div className="rounded-xl border border-white/10 bg-white/[0.02] px-4 py-6 text-center text-sm text-white/40">
            Nothing pending right now — check back soon, or grow your stats below to attract more.
          </div>
        ) : (
          <div className="space-y-2">
            {requests.map((r) => (
              <div key={r.id} className="flex flex-wrap items-center justify-between gap-3 rounded-xl border border-white/10 bg-white/[0.03] p-4">
                <div>
                  <p className="text-sm text-white/90">{r.message}</p>
                  <p className="mt-1 text-xs text-white/40">
                    Sent {new Date(r.created_at).toLocaleDateString()}
                  </p>
                </div>
                <div className="flex gap-2">
                  <button
                    onClick={() => void respond(r.id, false)}
                    disabled={busyId === r.id}
                    className="rounded-lg border border-white/15 px-3 py-1.5 text-xs font-medium text-white/70 hover:border-white/30 hover:text-white disabled:opacity-50"
                  >
                    Decline
                  </button>
                  <button
                    onClick={() => void respond(r.id, true)}
                    disabled={busyId === r.id}
                    className="rounded-lg bg-gradient-to-r from-violet-500 to-fuchsia-500 px-3 py-1.5 text-xs font-semibold hover:opacity-90 disabled:opacity-50"
                  >
                    {busyId === r.id ? "…" : "Accept"}
                  </button>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>

      {/* Stats */}
      <div>
        <h2 className="mb-3 text-lg font-semibold">Your momentum</h2>
        <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
          <StatChip label="Followers" value={metrics.follower_count != null ? metrics.follower_count.toLocaleString() : "—"} />
          <StatChip label="Engagement" value={pct(metrics.engagement_rate)} />
          <StatChip label="Response rate" value={pct(metrics.response_rate)} />
          <StatChip label="Avg rating" value={metrics.avg_rating != null ? `${metrics.avg_rating}★` : "—"} />
          <StatChip
            label="Collaborations"
            value={String(metrics.collaborations_total ?? 0)}
            hint={metrics.collaborations_active ? `${metrics.collaborations_active} active now` : undefined}
          />
          <StatChip label="Published" value={String(metrics.published_assets ?? 0)} />
          <StatChip
            label="Deliverables"
            value={`${metrics.deliverables_approved ?? 0}/${metrics.deliverables_total ?? 0}`}
          />
          <StatChip label="Reviews" value={String(metrics.review_count ?? 0)} />
        </div>
      </div>

      {/* Benchmarks */}
      {benchmarks.length > 0 ? (
        <div>
          <h2 className="mb-3 text-lg font-semibold">How you stack up</h2>
          <div className="space-y-2">
            {benchmarks.map((b) => (
              <div key={b.metric} className="rounded-xl border border-white/10 bg-white/[0.03] p-4">
                <div className="flex items-center justify-between text-sm">
                  <span className="capitalize text-white/70">{b.metric.replace(/_/g, " ")}</span>
                  <span
                    className={
                      b.verdict === "above" ? "text-emerald-300" : b.verdict === "below" ? "text-amber-300" : "text-white/50"
                    }
                  >
                    {b.verdict === "above" ? "Above average" : b.verdict === "below" ? "Below average" : "On par"}
                    {b.percentile != null ? ` · top ${100 - b.percentile}%` : ""}
                  </span>
                </div>
                <div className="mt-2 h-1.5 overflow-hidden rounded-full bg-white/10">
                  <div
                    className="h-full rounded-full bg-gradient-to-r from-violet-400 to-fuchsia-400"
                    style={{ width: `${Math.min(100, (b.you / Math.max(b.you, b.cohort_avg, 1)) * 100)}%` }}
                  />
                </div>
                <p className="mt-1 text-[11px] text-white/40">vs {b.cohort_size} peers in your industry & size</p>
              </div>
            ))}
          </div>
        </div>
      ) : null}

      {/* Level-up recommendations */}
      <div>
        <h2 className="mb-3 text-lg font-semibold">Level up</h2>
        {recommendations.length === 0 ? (
          <div className="rounded-xl border border-emerald-400/20 bg-emerald-500/10 px-4 py-4 text-sm text-emerald-200">
            You&apos;re doing great — nothing urgent to fix right now. 🎉
          </div>
        ) : (
          <div className="space-y-2">
            {recommendations.map((r, i) => (
              <div key={i} className={`rounded-xl border p-4 ${PRIORITY_GLOW[r.priority]}`}>
                <div className="flex items-center gap-2 text-xs font-medium text-white/60">
                  {PRIORITY_BADGE[r.priority]}
                </div>
                <p className="mt-1 font-semibold">{r.title}</p>
                <p className="text-sm text-white/60">{r.detail}</p>
              </div>
            ))}
          </div>
        )}
      </div>

      <PublicPagePanel creator={creator} />
    </div>
  );
}
