"use client";

import { useBrand } from "@/lib/brand";

export function BrandSelector() {
  const { brands, selectedBrandId, setSelectedBrandId } = useBrand();

  return (
    <label className="flex items-center gap-2 text-sm">
      <span className="hidden text-white/50 sm:inline">Brand</span>
      <select
        value={selectedBrandId ?? ""}
        onChange={(e) => setSelectedBrandId(e.target.value || null)}
        className="rounded-lg border border-white/15 bg-white/[0.06] px-3 py-1.5 text-sm text-white/80 focus:border-violet-400 focus:outline-none focus:ring-1 focus:ring-violet-400 [&>option]:bg-[#16121f] [&>option]:text-white"
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
