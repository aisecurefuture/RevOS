"use client";

import { useCallback, useEffect, useState } from "react";

import { MetricCard } from "@/components/MetricCard";
import { PageHeader } from "@/components/PageHeader";
import { Card, CardTitle } from "@/components/ui/Card";
import { Spinner } from "@/components/ui/Spinner";
import { ApiError } from "@/lib/api";
import { useBrand } from "@/lib/brand";
import { analyticsApi } from "@/lib/resources";
import type { AnalyticsOverview } from "@/lib/types";

function usd(cents: number): string {
  return (cents / 100).toLocaleString(undefined, { style: "currency", currency: "USD" });
}

export default function OverviewPage() {
  const { selectedBrandId } = useBrand();
  const [justSubscribed, setJustSubscribed] = useState(false);
  useEffect(() => {
    setJustSubscribed(new URLSearchParams(window.location.search).get("subscribed") === "1");
  }, []);
  const [data, setData] = useState<AnalyticsOverview | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      setData(await analyticsApi.overview(selectedBrandId));
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Failed to load dashboard");
    } finally {
      setLoading(false);
    }
  }, [selectedBrandId]);

  useEffect(() => {
    void load();
  }, [load]);

  return (
    <>
      {justSubscribed && (
        <div className="mb-4 rounded-xl bg-green-50 border border-green-200 px-4 py-3 text-sm text-green-800">
          Welcome to RevOS! Your subscription is active. You&apos;re all set.
        </div>
      )}
      <PageHeader
        title="Overview"
        description="Revenue, leads, and pipeline at a glance — across the selected brand."
      />
      {error ? (
        <div className="mb-4 rounded-lg bg-red-50 px-3 py-2 text-sm text-red-700">{error}</div>
      ) : null}

      {loading || !data ? (
        <Spinner />
      ) : (
        <>
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 xl:grid-cols-4">
            <MetricCard label="Revenue (MTD)" value={usd(data.revenue_mtd_cents)} />
            <MetricCard label="New Leads (30d)" value={String(data.new_leads_30d)} />
            <MetricCard
              label="Subscribers"
              value={String(data.subscribers)}
              hint="Confirmed opt-ins"
            />
            <MetricCard label="Pipeline Value" value={usd(data.pipeline_value_cents)} />
          </div>

          <div className="mt-6 grid grid-cols-1 gap-4 lg:grid-cols-2">
            <Card>
              <CardTitle>Leads by source</CardTitle>
              <BarList
                items={data.leads_by_source.map((s) => ({ label: s.source, value: s.count }))}
              />
            </Card>
            <Card>
              <CardTitle>Funnel</CardTitle>
              <BarList items={data.funnel.map((s) => ({ label: s.stage, value: s.count }))} />
            </Card>
            <Card>
              <CardTitle>Email performance</CardTitle>
              <div className="grid grid-cols-3 gap-2 text-center">
                <Stat label="Sent" value={data.email.sent} />
                <Stat label="Open rate" value={`${Math.round(data.email.open_rate * 100)}%`} />
                <Stat label="Click rate" value={`${Math.round(data.email.click_rate * 100)}%`} />
              </div>
            </Card>
            <Card>
              <CardTitle>Tasks requiring approval</CardTitle>
              <p className="text-3xl font-semibold text-slate-900">{data.pending_approvals}</p>
              <p className="mt-1 text-xs text-slate-400">Pending in the approval queue</p>
            </Card>
            <Card className="lg:col-span-2">
              <CardTitle>Recent activity</CardTitle>
              {data.recent_activity.length === 0 ? (
                <p className="text-sm text-slate-400">No activity yet.</p>
              ) : (
                <ul className="space-y-1 text-sm text-slate-600">
                  {data.recent_activity.map((a, i) => (
                    <li key={i} className="flex justify-between">
                      <span>
                        {a.action}
                        {a.entity_type ? ` · ${a.entity_type}` : ""}
                      </span>
                      <span className="text-xs text-slate-400">
                        {new Date(a.at).toLocaleString()}
                      </span>
                    </li>
                  ))}
                </ul>
              )}
            </Card>
          </div>
        </>
      )}
    </>
  );
}

function Stat({ label, value }: { label: string; value: string | number }) {
  return (
    <div>
      <p className="text-2xl font-semibold text-slate-900">{value}</p>
      <p className="text-xs text-slate-400">{label}</p>
    </div>
  );
}

function BarList({ items }: { items: { label: string; value: number }[] }) {
  const max = Math.max(1, ...items.map((i) => i.value));
  if (items.length === 0) return <p className="text-sm text-slate-400">No data yet.</p>;
  return (
    <div className="space-y-2">
      {items.map((item) => (
        <div key={item.label}>
          <div className="mb-0.5 flex justify-between text-xs text-slate-500">
            <span className="capitalize">{item.label}</span>
            <span>{item.value}</span>
          </div>
          <div className="h-2 rounded-full bg-slate-100">
            <div
              className="h-2 rounded-full bg-brand"
              style={{ width: `${(item.value / max) * 100}%` }}
            />
          </div>
        </div>
      ))}
    </div>
  );
}
