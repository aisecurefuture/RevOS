"use client";

// The one brand-creation form, shared by the Brands page and the zero-brands
// onboarding — the minimum fields to reach a usable state (name + type;
// website optional). Everything downstream inherits from what's created here.

import { useState } from "react";

import { IndustryPicker } from "@/components/IndustryPicker";
import { Button } from "@/components/ui/Button";
import { ApiError } from "@/lib/api";
import { isRegulated } from "@/lib/industries";
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
  const [industry, setIndustry] = useState("");
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
        industry: industry || undefined,
        website_url: website || undefined,
      });
      setName("");
      setWebsite("");
      setIndustry("");
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
      <div className="w-56">
        <label className="mb-1 block text-xs font-medium text-slate-500">Industry</label>
        <IndustryPicker value={industry} onChange={setIndustry} />
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
      {isRegulated(industry) ? (
        <p className="w-full text-xs text-amber-600">
          Heads up: your industry has advertising/compliance rules. RevOS helps you set
          disclaimers and guardrails in the Brand Book, but you&apos;re responsible for
          what you publish — it isn&apos;t automatically compliant.
        </p>
      ) : null}
      {error ? <p className="w-full text-xs text-red-600">{error}</p> : null}
    </form>
  );
}
