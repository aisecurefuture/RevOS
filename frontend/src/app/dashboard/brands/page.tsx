"use client";

import { useCallback, useEffect, useState } from "react";

import { PageHeader } from "@/components/PageHeader";
import { Button } from "@/components/ui/Button";
import { Card } from "@/components/ui/Card";
import { Spinner } from "@/components/ui/Spinner";
import { ApiError } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { brandsApi } from "@/lib/resources";
import type { Brand } from "@/lib/types";

const BRAND_TYPES = ["company", "personal", "book", "influencer", "product"];

export default function BrandsPage() {
  const { user } = useAuth();
  const canManage = user?.role === "admin" || user?.role === "owner";

  const [brands, setBrands] = useState<Brand[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const [name, setName] = useState("");
  const [brandType, setBrandType] = useState("company");
  const [website, setWebsite] = useState("");
  const [saving, setSaving] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      setBrands(await brandsApi.list());
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Failed to load brands");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  async function create(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    setSaving(true);
    try {
      await brandsApi.create({
        name,
        brand_type: brandType,
        website_url: website || undefined,
      });
      setName("");
      setWebsite("");
      await load();
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Failed to create brand");
    } finally {
      setSaving(false);
    }
  }

  async function remove(id: string) {
    if (!confirm("Delete this brand?")) return;
    try {
      await brandsApi.remove(id);
      await load();
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Failed to delete brand");
    }
  }

  return (
    <>
      <PageHeader title="Brands" description="Your businesses, books, and personal brand." />

      {error ? (
        <div className="mb-4 rounded-lg bg-red-50 px-3 py-2 text-sm text-red-700">{error}</div>
      ) : null}

      {canManage ? (
        <Card className="mb-6">
          <form onSubmit={create} className="flex flex-wrap items-end gap-3">
            <div className="grow">
              <label className="mb-1 block text-xs font-medium text-slate-500">Name</label>
              <input
                required
                value={name}
                onChange={(e) => setName(e.target.value)}
                placeholder="CyberArmor.ai"
                className="w-full rounded-lg border border-slate-300 px-3 py-2 text-sm focus:border-brand focus:outline-none focus:ring-1 focus:ring-brand"
              />
            </div>
            <div>
              <label className="mb-1 block text-xs font-medium text-slate-500">Type</label>
              <select
                value={brandType}
                onChange={(e) => setBrandType(e.target.value)}
                className="rounded-lg border border-slate-300 px-3 py-2 text-sm focus:border-brand focus:outline-none"
              >
                {BRAND_TYPES.map((t) => (
                  <option key={t} value={t}>
                    {t}
                  </option>
                ))}
              </select>
            </div>
            <div className="grow">
              <label className="mb-1 block text-xs font-medium text-slate-500">Website</label>
              <input
                value={website}
                onChange={(e) => setWebsite(e.target.value)}
                placeholder="https://cyberarmor.ai"
                className="w-full rounded-lg border border-slate-300 px-3 py-2 text-sm focus:border-brand focus:outline-none focus:ring-1 focus:ring-brand"
              />
            </div>
            <Button type="submit" disabled={saving}>
              {saving ? "Adding…" : "Add brand"}
            </Button>
          </form>
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
                <th className="px-4 py-3">Slug</th>
                <th className="px-4 py-3">Website</th>
                {canManage ? <th className="px-4 py-3" /> : null}
              </tr>
            </thead>
            <tbody>
              {brands.length === 0 ? (
                <tr>
                  <td colSpan={5} className="px-4 py-6 text-center text-slate-400">
                    No brands yet.
                  </td>
                </tr>
              ) : (
                brands.map((b) => (
                  <tr key={b.id} className="border-b border-slate-100 last:border-0">
                    <td className="px-4 py-3 font-medium text-slate-800">{b.name}</td>
                    <td className="px-4 py-3 capitalize text-slate-500">{b.brand_type}</td>
                    <td className="px-4 py-3 text-slate-500">{b.slug}</td>
                    <td className="px-4 py-3 text-slate-500">{b.website_url || "—"}</td>
                    {canManage ? (
                      <td className="px-4 py-3 text-right">
                        <Button variant="ghost" onClick={() => void remove(b.id)}>
                          Delete
                        </Button>
                      </td>
                    ) : null}
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
