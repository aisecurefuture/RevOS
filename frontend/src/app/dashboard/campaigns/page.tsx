"use client";

import { useCallback, useEffect, useState } from "react";

import { PageHeader } from "@/components/PageHeader";
import { Button } from "@/components/ui/Button";
import { Card } from "@/components/ui/Card";
import { Spinner } from "@/components/ui/Spinner";
import { ApiError } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { useBrand } from "@/lib/brand";
import { campaignsApi } from "@/lib/resources";
import type { Campaign } from "@/lib/types";

const CHANNELS = ["email", "social", "landing", "multi", "ads"];

export default function CampaignsPage() {
  const { user } = useAuth();
  const { selectedBrandId, brands } = useBrand();
  const canEdit = user ? user.role !== "viewer" : false;

  const [items, setItems] = useState<Campaign[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [name, setName] = useState("");
  const [channel, setChannel] = useState("email");
  const [saving, setSaving] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      setItems(await campaignsApi.list(selectedBrandId));
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Failed to load campaigns");
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
    setError(null);
    setSaving(true);
    try {
      await campaignsApi.create({ brand_id: selectedBrandId, name, channel });
      setName("");
      await load();
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Failed to create campaign");
    } finally {
      setSaving(false);
    }
  }

  return (
    <>
      <PageHeader
        title="Campaigns"
        description="Campaigns by brand. Landing pages & forms attach in Module 6."
      />

      {error ? (
        <div className="mb-4 rounded-lg bg-red-50 px-3 py-2 text-sm text-red-700">{error}</div>
      ) : null}

      {canEdit ? (
        <Card className="mb-6">
          {selectedBrandId ? (
            <form onSubmit={create} className="flex flex-wrap items-end gap-3">
              <div className="grow">
                <label className="mb-1 block text-xs font-medium text-slate-500">Campaign name</label>
                <input
                  required
                  value={name}
                  onChange={(e) => setName(e.target.value)}
                  placeholder="Book launch"
                  className="w-full rounded-lg border border-slate-300 px-3 py-2 text-sm focus:border-brand focus:outline-none focus:ring-1 focus:ring-brand"
                />
              </div>
              <div>
                <label className="mb-1 block text-xs font-medium text-slate-500">Channel</label>
                <select
                  value={channel}
                  onChange={(e) => setChannel(e.target.value)}
                  className="rounded-lg border border-slate-300 px-3 py-2 text-sm focus:border-brand focus:outline-none"
                >
                  {CHANNELS.map((c) => (
                    <option key={c} value={c}>
                      {c}
                    </option>
                  ))}
                </select>
              </div>
              <Button type="submit" disabled={saving}>
                {saving ? "Adding…" : "Add campaign"}
              </Button>
            </form>
          ) : (
            <p className="text-sm text-slate-500">
              Select a specific brand in the top bar to create a campaign
              {brands.length === 0 ? " (add a brand first)" : ""}.
            </p>
          )}
        </Card>
      ) : null}

      {loading ? (
        <Spinner />
      ) : (
        <Card className="overflow-x-auto p-0">
          <table className="w-full text-sm">
            <thead className="border-b border-slate-200 text-left text-xs uppercase text-slate-400">
              <tr>
                <th className="px-4 py-3">Name</th>
                <th className="px-4 py-3">Channel</th>
                <th className="px-4 py-3">Status</th>
                <th className="px-4 py-3">Slug</th>
              </tr>
            </thead>
            <tbody>
              {items.length === 0 ? (
                <tr>
                  <td colSpan={4} className="px-4 py-6 text-center text-slate-400">
                    No campaigns yet.
                  </td>
                </tr>
              ) : (
                items.map((c) => (
                  <tr key={c.id} className="border-b border-slate-100 last:border-0">
                    <td className="px-4 py-3 font-medium text-slate-800">{c.name}</td>
                    <td className="px-4 py-3 capitalize text-slate-500">{c.channel}</td>
                    <td className="px-4 py-3 capitalize text-slate-500">{c.status}</td>
                    <td className="px-4 py-3 text-slate-500">{c.slug}</td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </Card>
      )}
    </>
  );
}
