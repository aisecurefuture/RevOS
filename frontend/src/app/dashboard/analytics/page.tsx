"use client";

import { useCallback, useEffect, useState } from "react";

import { PageHeader } from "@/components/PageHeader";
import { Button } from "@/components/ui/Button";
import { Card, CardTitle } from "@/components/ui/Card";
import { Spinner } from "@/components/ui/Spinner";
import { ApiError } from "@/lib/api";
import { useBrand } from "@/lib/brand";
import { analyticsApi } from "@/lib/resources";

function usd(cents: number): string {
  return (cents / 100).toLocaleString(undefined, { style: "currency", currency: "USD" });
}

export default function AnalyticsPage() {
  const { selectedBrandId } = useBrand();
  const [revenue, setRevenue] = useState<{ offer: string; amount_cents: number }[]>([]);
  const [pipeline, setPipeline] = useState<{ stage: string; count: number; amount_cents: number }[]>(
    [],
  );
  const [funnel, setFunnel] = useState<{ stage: string; count: number }[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const [r, p, f] = await Promise.all([
        analyticsApi.revenue(selectedBrandId),
        analyticsApi.pipeline(selectedBrandId),
        analyticsApi.funnel(selectedBrandId),
      ]);
      setRevenue(r);
      setPipeline(p);
      setFunnel(f);
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Failed to load analytics");
    } finally {
      setLoading(false);
    }
  }, [selectedBrandId]);

  useEffect(() => {
    void load();
  }, [load]);

  const totalRevenue = revenue.reduce((s, r) => s + r.amount_cents, 0);
  const totalPipeline = pipeline.reduce((s, p) => s + p.amount_cents, 0);

  return (
    <>
      <PageHeader
        title="Analytics"
        description="Revenue intelligence & funnel performance."
        actions={
          <Button variant="secondary" onClick={() => void analyticsApi.exportCsv(selectedBrandId)}>
            Export CSV
          </Button>
        }
      />
      {error ? (
        <div className="mb-4 rounded-lg bg-red-50 px-3 py-2 text-sm text-red-700">{error}</div>
      ) : null}

      {loading ? (
        <Spinner />
      ) : (
        <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
          <Card>
            <CardTitle>Revenue by offer · {usd(totalRevenue)}</CardTitle>
            {revenue.length === 0 ? (
              <p className="text-sm text-slate-400">No revenue recorded yet.</p>
            ) : (
              <ul className="space-y-1 text-sm">
                {revenue.map((r) => (
                  <li key={r.offer} className="flex justify-between">
                    <span className="text-slate-600">{r.offer}</span>
                    <span className="font-medium text-slate-800">{usd(r.amount_cents)}</span>
                  </li>
                ))}
              </ul>
            )}
          </Card>

          <Card>
            <CardTitle>Funnel</CardTitle>
            <ul className="space-y-1 text-sm">
              {funnel.map((f) => (
                <li key={f.stage} className="flex justify-between">
                  <span className="text-slate-600">{f.stage}</span>
                  <span className="font-medium text-slate-800">{f.count}</span>
                </li>
              ))}
            </ul>
          </Card>

          <Card className="lg:col-span-2">
            <CardTitle>Pipeline · {usd(totalPipeline)} open</CardTitle>
            <div className="flex gap-3 overflow-x-auto">
              {pipeline.map((p) => (
                <div
                  key={p.stage}
                  className="w-40 shrink-0 rounded-lg border border-slate-200 p-3"
                >
                  <p className="text-xs font-semibold text-slate-700">{p.stage}</p>
                  <p className="mt-1 text-lg font-semibold text-slate-900">{p.count}</p>
                  <p className="text-xs text-slate-400">{usd(p.amount_cents)}</p>
                </div>
              ))}
            </div>
          </Card>
        </div>
      )}
    </>
  );
}
