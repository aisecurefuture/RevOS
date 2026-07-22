"use client";

import { useCallback, useEffect, useState } from "react";

import { Card, CardTitle } from "@/components/ui/Card";
import { Spinner } from "@/components/ui/Spinner";
import { ApiError } from "@/lib/api";
import { marketplaceApi } from "@/lib/resources";
import type {
  InsightBenchmark,
  InsightRecommendation,
  Insights,
  MatchCreator,
  MatchProduct,
  ReputationScore,
} from "@/lib/types";

type Kind = "creators" | "products";

function scoreColor(v: number): string {
  if (v >= 75) return "text-green-600";
  if (v >= 55) return "text-blue-600";
  if (v >= 35) return "text-amber-600";
  return "text-slate-400";
}

function ReputationCard({ rep }: { rep: ReputationScore }) {
  return (
    <Card>
      <CardTitle>Reputation</CardTitle>
      <div className="flex items-center gap-4">
        <div className="text-center">
          <div className={`text-4xl font-bold ${scoreColor(rep.overall)}`}>
            {Math.round(rep.overall)}
          </div>
          <div className="text-xs text-slate-400">out of 100</div>
        </div>
        <div className="grow">
          <p className="mb-2 text-xs text-slate-600">{rep.rationale}</p>
          <div className="space-y-1.5">
            {rep.dimensions.map((d) => (
              <div key={d.key} className="flex items-center gap-2">
                <span className="w-32 shrink-0 text-xs capitalize text-slate-500">
                  {d.key.replace(/_/g, " ")}
                </span>
                <div className="h-2 grow overflow-hidden rounded-full bg-slate-100">
                  <div
                    className={`h-full rounded-full ${d.available ? "bg-brand" : "bg-slate-200"}`}
                    style={{ width: `${d.available ? d.score : 0}%` }}
                  />
                </div>
                <span className="w-8 shrink-0 text-right text-xs text-slate-500">
                  {d.available ? Math.round(d.score) : "—"}
                </span>
              </div>
            ))}
          </div>
          <p className="mt-2 text-xs text-slate-400">
            {Math.round(rep.coverage * 100)}% data coverage · {rep.review_count} review
            {rep.review_count === 1 ? "" : "s"}
          </p>
        </div>
      </div>
    </Card>
  );
}

function StatTile({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-lg border border-slate-200 bg-white p-3">
      <div className="text-lg font-semibold text-slate-800">{value}</div>
      <div className="text-xs text-slate-500">{label}</div>
    </div>
  );
}

function pct(v: number | null | undefined): string {
  return v == null ? "—" : `${Math.round(v * 100)}%`;
}

function MetricTiles({ m }: { m: Record<string, number | null> }) {
  return (
    <div className="grid grid-cols-2 gap-2 sm:grid-cols-3">
      <StatTile label="Response rate" value={pct(m.response_rate)} />
      <StatTile label="Acceptance rate" value={pct(m.acceptance_rate)} />
      <StatTile label="Requests received" value={String(m.requests_received ?? 0)} />
      <StatTile label="Requests sent" value={String(m.requests_sent ?? 0)} />
      <StatTile label="Avg rating" value={m.avg_rating != null ? `${m.avg_rating}/5` : "—"} />
      {m.engagement_rate != null ? (
        <StatTile label="Engagement" value={pct(m.engagement_rate)} />
      ) : null}
      {m.follower_count != null ? (
        <StatTile label="Followers" value={m.follower_count.toLocaleString()} />
      ) : null}
      {m.collaborations_total != null ? (
        <StatTile label="Collaborations" value={`${m.collaborations_total} (${m.collaborations_active ?? 0} active)`} />
      ) : null}
      {m.published_assets != null ? (
        <StatTile label="Published from workspace" value={String(m.published_assets)} />
      ) : null}
      {m.deliverables_total ? (
        <StatTile
          label="Deliverables"
          value={`${m.deliverables_approved ?? 0}/${m.deliverables_total} approved`}
        />
      ) : null}
    </div>
  );
}

const VERDICT_STYLE: Record<string, string> = {
  above: "text-green-600",
  below: "text-red-600",
  on_par: "text-slate-500",
};

function BenchmarkRow({ b }: { b: InsightBenchmark }) {
  const isRate = b.metric === "engagement_rate";
  const fmt = (v: number) => (isRate ? `${(v * 100).toFixed(1)}%` : v.toLocaleString());
  const label = b.metric.replace(/_/g, " ");
  const fromReport = b.source === "industry_report";
  return (
    <div className="border-b border-slate-100 py-2 last:border-0">
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <span className="text-sm capitalize text-slate-700">{label}</span>
        <span className="text-xs text-slate-500">
          You <b className={VERDICT_STYLE[b.verdict]}>{fmt(b.you)}</b> ·{" "}
          {fromReport ? "industry avg" : "cohort avg"} {fmt(b.cohort_avg)}
          {b.percentile != null ? ` · top ${100 - b.percentile}%` : ""}
          {!fromReport ? <span className="ml-1 text-slate-400">({b.cohort_size} peers)</span> : null}
        </span>
      </div>
      {fromReport && b.citation ? (
        <p className="mt-0.5 text-right text-[11px] text-slate-400">Source: {b.citation}</p>
      ) : null}
    </div>
  );
}

const PRIORITY_STYLE: Record<string, string> = {
  high: "border-l-red-500 bg-red-50",
  medium: "border-l-amber-500 bg-amber-50",
  low: "border-l-slate-300 bg-slate-50",
};

function RecCard({ r }: { r: InsightRecommendation }) {
  return (
    <div className={`rounded-lg border-l-4 px-3 py-2 ${PRIORITY_STYLE[r.priority]}`}>
      <div className="text-sm font-medium text-slate-800">{r.title}</div>
      <div className="text-xs text-slate-600">{r.detail}</div>
    </div>
  );
}

export function InsightsTab() {
  const [kind, setKind] = useState<Kind>("creators");
  const [creators, setCreators] = useState<MatchCreator[]>([]);
  const [products, setProducts] = useState<MatchProduct[]>([]);
  const [selectedId, setSelectedId] = useState("");
  const [insights, setInsights] = useState<Insights | null>(null);
  const [loadingRoster, setLoadingRoster] = useState(true);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    void (async () => {
      try {
        const [c, p] = await Promise.all([
          marketplaceApi.myCreators({ limit: "100" }),
          marketplaceApi.myProducts({ limit: "100" }),
        ]);
        setCreators(c);
        setProducts(p);
      } catch (e) {
        setError(e instanceof ApiError ? e.message : "Failed to load your roster");
      } finally {
        setLoadingRoster(false);
      }
    })();
  }, []);

  const roster = kind === "creators" ? creators : products;

  const load = useCallback(async (id: string, k: Kind) => {
    if (!id) {
      setInsights(null);
      return;
    }
    setLoading(true);
    setError(null);
    try {
      setInsights(
        k === "creators"
          ? await marketplaceApi.creatorInsights(id)
          : await marketplaceApi.productInsights(id),
      );
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Failed to load insights");
      setInsights(null);
    } finally {
      setLoading(false);
    }
  }, []);

  function switchKind(k: Kind) {
    setKind(k);
    setSelectedId("");
    setInsights(null);
  }

  function pick(id: string) {
    setSelectedId(id);
    void load(id, kind);
  }

  if (loadingRoster) return <Spinner />;

  return (
    <div className="space-y-4">
      {error ? (
        <div className="rounded-lg bg-red-50 px-3 py-2 text-sm text-red-700">{error}</div>
      ) : null}

      <Card>
        <div className="flex flex-wrap items-end gap-3">
          <div className="flex gap-2">
            {(["creators", "products"] as Kind[]).map((k) => (
              <button
                key={k}
                type="button"
                onClick={() => switchKind(k)}
                className={`rounded-lg px-3 py-1.5 text-sm font-medium capitalize ${
                  kind === k ? "bg-brand text-white" : "border border-slate-200 bg-white text-slate-600"
                }`}
              >
                {k}
              </button>
            ))}
          </div>
          <div className="grow">
            <label className="mb-1 block text-xs font-medium text-slate-500">
              Select one of your {kind} to see its dashboard
            </label>
            <select
              value={selectedId}
              onChange={(e) => pick(e.target.value)}
              className="w-full rounded-lg border border-slate-300 px-3 py-2 text-sm"
            >
              <option value="">Choose…</option>
              {roster.map((o) => (
                <option key={o.id} value={o.id}>
                  {"name" in o ? (o as MatchProduct).name : (o as MatchCreator).display_name}
                </option>
              ))}
            </select>
          </div>
        </div>
        {roster.length === 0 ? (
          <p className="mt-2 text-xs text-slate-400">
            No {kind} yet — add some under “My roster” first.
          </p>
        ) : null}
      </Card>

      {loading ? <Spinner /> : null}

      {insights && !loading ? (
        <>
          <div className="text-sm text-slate-500">
            {insights.subject.name}
            {insights.subject.industry ? ` · ${insights.subject.industry.replace(/_/g, " ")}` : ""}
            {insights.subject.size_tier ? ` · ${insights.subject.size_tier}` : ""}
          </div>

          <ReputationCard rep={insights.reputation} />

          <Card>
            <CardTitle>Performance</CardTitle>
            <MetricTiles m={insights.metrics} />
          </Card>

          {insights.benchmarks.length > 0 ? (
            <Card>
              <CardTitle>How you compare to your cohort</CardTitle>
              {insights.benchmarks.map((b) => (
                <BenchmarkRow key={b.metric} b={b} />
              ))}
            </Card>
          ) : null}

          <Card>
            <CardTitle>What to work on</CardTitle>
            {insights.recommendations.length === 0 ? (
              <p className="text-sm text-slate-400">
                Nothing urgent — your profile is in good shape. 🎉
              </p>
            ) : (
              <div className="space-y-2">
                {insights.recommendations.map((r, i) => (
                  <RecCard key={i} r={r} />
                ))}
              </div>
            )}
          </Card>
        </>
      ) : null}
    </div>
  );
}
