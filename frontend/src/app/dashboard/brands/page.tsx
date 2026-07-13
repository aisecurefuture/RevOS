"use client";

import { useCallback, useEffect, useState } from "react";

import { BrandCreateForm } from "@/components/BrandCreateForm";
import { PageHeader } from "@/components/PageHeader";
import { Button } from "@/components/ui/Button";
import { Card } from "@/components/ui/Card";
import { Spinner } from "@/components/ui/Spinner";
import { ApiError } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { useBrand } from "@/lib/brand";
import { brandsApi } from "@/lib/resources";
import type { Brand } from "@/lib/types";

export default function BrandsPage() {
  const { user } = useAuth();
  const { refresh: refreshGlobal } = useBrand();
  const canManage = user?.role === "admin" || user?.role === "owner";

  const [brands, setBrands] = useState<Brand[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

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
          <BrandCreateForm onCreated={async () => { await load(); await refreshGlobal(); }} />
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
