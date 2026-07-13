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
import { offersApi } from "@/lib/resources";
import type { Offer } from "@/lib/types";

const OFFER_TYPES = [
  "product",
  "book",
  "service",
  "lead_magnet",
  "course",
  "consulting",
  "digital",
];

function formatPrice(cents?: number | null, currency = "USD"): string {
  if (cents === null || cents === undefined) return "—";
  return `${(cents / 100).toLocaleString(undefined, { style: "currency", currency })}`;
}

export default function OffersPage() {
  const { user } = useAuth();
  const { selectedBrandId, brands } = useBrand();
  const canEdit = user ? user.role !== "viewer" : false;

  const [items, setItems] = useState<Offer[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [name, setName] = useState("");
  const [offerType, setOfferType] = useState("lead_magnet");
  const [price, setPrice] = useState("");
  const [saving, setSaving] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      setItems(await offersApi.list(selectedBrandId));
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Failed to load offers");
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
      const cents = price ? Math.round(parseFloat(price) * 100) : undefined;
      await offersApi.create({
        brand_id: selectedBrandId,
        name,
        offer_type: offerType,
        price_cents: cents,
      });
      setName("");
      setPrice("");
      await load();
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Failed to create offer");
    } finally {
      setSaving(false);
    }
  }

  return (
    <>
      <PageHeader
        title="Offers"
        description="Products, books, services, lead magnets — the catalog behind every funnel."
      />

      {error ? (
        <div className="mb-4 rounded-lg bg-red-50 px-3 py-2 text-sm text-red-700">{error}</div>
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
                  placeholder="AI Security Checklist"
                  className="w-full rounded-lg border border-slate-300 px-3 py-2 text-sm focus:border-brand focus:outline-none focus:ring-1 focus:ring-brand"
                />
              </div>
              <div>
                <label className="mb-1 block text-xs font-medium text-slate-500">Type</label>
                <select
                  value={offerType}
                  onChange={(e) => setOfferType(e.target.value)}
                  className="rounded-lg border border-slate-300 px-3 py-2 text-sm focus:border-brand focus:outline-none"
                >
                  {OFFER_TYPES.map((t) => (
                    <option key={t} value={t}>
                      {t}
                    </option>
                  ))}
                </select>
              </div>
              <div className="w-28">
                <label className="mb-1 block text-xs font-medium text-slate-500">Price (USD)</label>
                <input
                  type="number"
                  min="0"
                  step="0.01"
                  value={price}
                  onChange={(e) => setPrice(e.target.value)}
                  placeholder="0.00"
                  className="w-full rounded-lg border border-slate-300 px-3 py-2 text-sm focus:border-brand focus:outline-none focus:ring-1 focus:ring-brand"
                />
              </div>
              <Button type="submit" disabled={saving}>
                {saving ? "Adding…" : "Add offer"}
              </Button>
            </form>
          ) : (
            brands.length === 0 ? (
              <NoBrandCta feature="Offers" />
            ) : (
              <p className="text-sm text-slate-500">
                Select a specific brand in the top bar to create an offer.
              </p>
            )
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
                <th className="px-4 py-3">Type</th>
                <th className="px-4 py-3">Price</th>
                <th className="px-4 py-3">Status</th>
              </tr>
            </thead>
            <tbody>
              {items.length === 0 ? (
                <tr>
                  <td colSpan={4} className="px-4 py-6 text-center text-slate-400">
                    No offers yet.
                  </td>
                </tr>
              ) : (
                items.map((o) => (
                  <tr key={o.id} className="border-b border-slate-100 last:border-0">
                    <td className="px-4 py-3 font-medium text-slate-800">{o.name}</td>
                    <td className="px-4 py-3 text-slate-500">{o.offer_type.replace("_", " ")}</td>
                    <td className="px-4 py-3 text-slate-500">
                      {formatPrice(o.price_cents, o.currency)}
                    </td>
                    <td className="px-4 py-3 capitalize text-slate-500">{o.status}</td>
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
