"use client";

import { useCallback, useEffect, useState } from "react";

import { NoBrandCta } from "@/components/NoBrandCta";
import { PageHeader } from "@/components/PageHeader";
import { Button } from "@/components/ui/Button";
import { Card } from "@/components/ui/Card";
import { Spinner } from "@/components/ui/Spinner";
import { ApiError } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { useBrand } from "@/lib/brand";
import { sequencesApi } from "@/lib/resources";
import type { Sequence } from "@/lib/types";

const TYPES = [
  "welcome", "book_launch", "consulting_nurture", "cyberarmor_buyer",
  "logistics_customer", "founder_newsletter", "reengagement",
  "abandoned_inquiry", "event_followup", "custom",
];

const STATUS_STYLES: Record<string, string> = {
  active: "bg-green-100 text-green-700",
  draft: "bg-slate-100 text-slate-500",
  paused: "bg-amber-100 text-amber-700",
  archived: "bg-slate-100 text-slate-400",
};

export default function SequencesPage() {
  const { user } = useAuth();
  const { selectedBrandId, brands } = useBrand();
  const canEdit = user ? user.role !== "viewer" : false;
  const isAdmin = user?.role === "admin" || user?.role === "owner";

  const [items, setItems] = useState<Sequence[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [name, setName] = useState("");
  const [type, setType] = useState("welcome");
  const [saving, setSaving] = useState(false);
  const [detail, setDetail] = useState<Sequence | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      setItems(await sequencesApi.list(selectedBrandId));
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Failed to load sequences");
    } finally {
      setLoading(false);
    }
  }, [selectedBrandId]);

  useEffect(() => {
    void load();
  }, [load]);

  async function create(e: React.FormEvent) {
    e.preventDefault();
    if (!selectedBrandId) return;
    setSaving(true);
    setError(null);
    try {
      await sequencesApi.create({ brand_id: selectedBrandId, name, sequence_type: type });
      setName("");
      await load();
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Create failed");
    } finally {
      setSaving(false);
    }
  }

  async function toggle(s: Sequence) {
    try {
      if (s.status === "active") await sequencesApi.pause(s.id);
      else await sequencesApi.activate(s.id);
      await load();
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Update failed");
    }
  }

  async function openDetail(id: string) {
    setDetail(await sequencesApi.get(id));
  }

  async function runTick() {
    setNotice(null);
    try {
      const r = await sequencesApi.tick();
      setNotice(`Tick: ${r.sent} sent, ${r.completed} completed, ${r.awaiting_approval} awaiting approval.`);
      await load();
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Tick failed");
    }
  }

  return (
    <>
      <PageHeader
        title="Sequences"
        description="Automated multi-step nurtures. Steps can be approval-gated; runs on a beat."
        actions={
          isAdmin ? (
            <Button variant="secondary" onClick={() => void runTick()}>
              Run tick now
            </Button>
          ) : undefined
        }
      />

      {error ? (
        <div className="mb-4 rounded-lg bg-red-50 px-3 py-2 text-sm text-red-700">{error}</div>
      ) : null}
      {notice ? (
        <div className="mb-4 rounded-lg bg-blue-50 px-3 py-2 text-sm text-blue-700">{notice}</div>
      ) : null}

      {canEdit ? (
        <Card className="mb-6">
          {selectedBrandId ? (
            <form onSubmit={create} className="flex flex-wrap items-end gap-3">
              <div className="grow">
                <label className="mb-1 block text-xs font-medium text-slate-500">Name</label>
                <input
                  required
                  value={name}
                  onChange={(e) => setName(e.target.value)}
                  placeholder="Welcome sequence"
                  className="w-full rounded-lg border border-slate-300 px-3 py-2 text-sm focus:border-brand focus:outline-none focus:ring-1 focus:ring-brand"
                />
              </div>
              <div>
                <label className="mb-1 block text-xs font-medium text-slate-500">Type</label>
                <select
                  value={type}
                  onChange={(e) => setType(e.target.value)}
                  className="rounded-lg border border-slate-300 px-3 py-2 text-sm focus:border-brand focus:outline-none"
                >
                  {TYPES.map((t) => (
                    <option key={t} value={t}>
                      {t.replace(/_/g, " ")}
                    </option>
                  ))}
                </select>
              </div>
              <Button type="submit" disabled={saving}>
                {saving ? "Adding…" : "Add sequence"}
              </Button>
            </form>
          ) : (
            brands.length === 0 ? (
              <NoBrandCta feature="Sequences" />
            ) : (
              <p className="text-sm text-slate-500">
                Select a specific brand in the top bar to create a sequence.
              </p>
            )
          )}
        </Card>
      ) : null}

      {loading ? (
        <Spinner />
      ) : items.length === 0 ? (
        <Card>
          <p className="text-sm text-slate-400">No sequences yet.</p>
        </Card>
      ) : (
        <div className="space-y-3">
          {items.map((s) => (
            <Card key={s.id}>
              <div className="flex flex-wrap items-center justify-between gap-3">
                <button
                  className="text-left"
                  onClick={() => void openDetail(s.id)}
                  type="button"
                >
                  <span
                    className={`rounded-full px-2 py-0.5 text-xs font-medium ${STATUS_STYLES[s.status] ?? "bg-slate-100"}`}
                  >
                    {s.status}
                  </span>
                  <span className="ml-2 font-medium text-slate-800">{s.name}</span>
                  <span className="ml-2 text-xs text-slate-400">
                    {s.sequence_type.replace(/_/g, " ")}
                  </span>
                </button>
                {canEdit ? (
                  <Button variant="secondary" onClick={() => void toggle(s)}>
                    {s.status === "active" ? "Pause" : "Activate"}
                  </Button>
                ) : null}
              </div>
              {detail?.id === s.id ? (
                <div className="mt-3 border-t border-slate-100 pt-3">
                  <p className="mb-2 text-xs font-medium uppercase text-slate-400">Steps</p>
                  {(detail.steps ?? []).length === 0 ? (
                    <p className="text-sm text-slate-400">No steps yet.</p>
                  ) : (
                    <ol className="space-y-1 text-sm text-slate-600">
                      {(detail.steps ?? []).map((st) => (
                        <li key={st.id}>
                          {st.order_index + 1}. {st.name || "(unnamed)"} · {st.delay_minutes}m delay
                          {st.require_approval ? " · approval-gated" : ""}
                        </li>
                      ))}
                    </ol>
                  )}
                </div>
              ) : null}
            </Card>
          ))}
        </div>
      )}
    </>
  );
}
