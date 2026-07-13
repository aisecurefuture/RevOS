"use client";

// The one brand-creation form, shared by the Brands page and the zero-brands
// onboarding — the minimum fields to reach a usable state (name + type;
// website optional). Everything downstream inherits from what's created here.

import { useState } from "react";

import { Button } from "@/components/ui/Button";
import { ApiError } from "@/lib/api";
import { brandsApi } from "@/lib/resources";
import type { Brand } from "@/lib/types";

const BRAND_TYPES = ["company", "personal", "book", "influencer", "product"];

export function BrandCreateForm({
  onCreated,
  submitLabel = "Add brand",
}: {
  onCreated?: (brand: Brand) => void | Promise<void>;
  submitLabel?: string;
}) {
  const [name, setName] = useState("");
  const [brandType, setBrandType] = useState("company");
  const [website, setWebsite] = useState("");
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function create(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    setSaving(true);
    try {
      const brand = await brandsApi.create({
        name,
        brand_type: brandType,
        website_url: website || undefined,
      });
      setName("");
      setWebsite("");
      await onCreated?.(brand);
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Failed to create brand");
    } finally {
      setSaving(false);
    }
  }

  return (
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
        <label className="mb-1 block text-xs font-medium text-slate-500">Website (optional)</label>
        <input
          value={website}
          onChange={(e) => setWebsite(e.target.value)}
          placeholder="https://cyberarmor.ai"
          className="w-full rounded-lg border border-slate-300 px-3 py-2 text-sm focus:border-brand focus:outline-none focus:ring-1 focus:ring-brand"
        />
      </div>
      <Button type="submit" disabled={saving}>
        {saving ? "Adding…" : submitLabel}
      </Button>
      {error ? <p className="w-full text-xs text-red-600">{error}</p> : null}
    </form>
  );
}
