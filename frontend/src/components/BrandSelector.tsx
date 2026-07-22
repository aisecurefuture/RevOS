"use client";

import { useBrand } from "@/lib/brand";

export function BrandSelector() {
  const { brands, selectedBrandId, setSelectedBrandId } = useBrand();

  return (
    <label className="flex items-center gap-2 text-sm">
      <span className="hidden text-slate-500 sm:inline">Brand</span>
      <select
        value={selectedBrandId ?? ""}
        onChange={(e) => setSelectedBrandId(e.target.value || null)}
        className="rounded-lg border border-slate-300 bg-white px-3 py-1.5 text-sm text-slate-700 focus:border-brand focus:outline-none focus:ring-1 focus:ring-brand"
      >
        <option value="">All Brands</option>
        {brands.map((b) => (
          <option key={b.id} value={b.id}>
            {b.name}
          </option>
        ))}
      </select>
    </label>
  );
}
