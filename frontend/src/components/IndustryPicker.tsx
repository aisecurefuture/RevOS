"use client";

// Searchable, grouped industry picker with an always-available "Other" free
// text. A long flat <select> of 60+ professions is its own wall-of-links
// problem; this filters as you type and falls back to a custom value so no
// one is ever excluded.

import { useMemo, useRef, useState } from "react";

import { INDUSTRY_GROUPS, findIndustry } from "@/lib/industries";

export function IndustryPicker({
  value,
  onChange,
}: {
  value: string;
  onChange: (value: string) => void;
}) {
  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState("");
  const [custom, setCustom] = useState(false);
  const boxRef = useRef<HTMLDivElement>(null);

  const selectedLabel = findIndustry(value)?.label ?? (value || "");

  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase();
    return INDUSTRY_GROUPS.map((g) => ({
      ...g,
      industries: q
        ? g.industries.filter((i) => i.label.toLowerCase().includes(q))
        : g.industries,
    })).filter((g) => g.industries.length > 0);
  }, [query]);

  function pick(v: string) {
    onChange(v);
    setOpen(false);
    setQuery("");
  }

  if (custom) {
    return (
      <div className="flex gap-2">
        <input
          autoFocus
          value={value}
          onChange={(e) => onChange(e.target.value)}
          placeholder="Your industry"
          className="w-full rounded-lg border border-slate-300 px-3 py-2 text-sm focus:border-brand focus:outline-none focus:ring-1 focus:ring-brand"
        />
        <button
          type="button"
          onClick={() => { setCustom(false); onChange(""); }}
          className="whitespace-nowrap text-xs text-slate-400 hover:text-slate-600"
        >
          ← list
        </button>
      </div>
    );
  }

  return (
    <div ref={boxRef} className="relative">
      <button
        type="button"
        onClick={() => setOpen((o) => !o)}
        className="flex w-full items-center justify-between rounded-lg border border-slate-300 px-3 py-2 text-left text-sm focus:border-brand focus:outline-none focus:ring-1 focus:ring-brand"
      >
        <span className={selectedLabel ? "text-slate-800" : "text-slate-400"}>
          {selectedLabel || "Select your industry…"}
        </span>
        <span aria-hidden className="text-slate-400">▾</span>
      </button>

      {open ? (
        <>
          {/* click-away */}
          <div className="fixed inset-0 z-10" onClick={() => setOpen(false)} aria-hidden />
          <div className="absolute z-20 mt-1 max-h-72 w-full overflow-y-auto rounded-lg border border-slate-200 bg-white shadow-lg">
            <div className="sticky top-0 border-b border-slate-100 bg-white p-2">
              <input
                autoFocus
                value={query}
                onChange={(e) => setQuery(e.target.value)}
                placeholder="Search industries…"
                className="w-full rounded-md border border-slate-200 px-2.5 py-1.5 text-sm focus:border-brand focus:outline-none"
              />
            </div>
            {filtered.map((g) => (
              <div key={g.category}>
                <div className="px-3 pt-2 pb-1 text-[10px] font-semibold uppercase tracking-widest text-slate-400">
                  {g.label}
                </div>
                {g.industries.map((i) => (
                  <button
                    key={i.value}
                    type="button"
                    onClick={() => pick(i.value)}
                    className={`block w-full px-3 py-1.5 text-left text-sm hover:bg-slate-50 ${
                      value === i.value ? "text-brand" : "text-slate-700"
                    }`}
                  >
                    {i.label}
                  </button>
                ))}
              </div>
            ))}
            <button
              type="button"
              onClick={() => { setCustom(true); setOpen(false); setQuery(""); onChange(""); }}
              className="block w-full border-t border-slate-100 px-3 py-2 text-left text-sm text-slate-500 hover:bg-slate-50"
            >
              + Other (type your own)
            </button>
          </div>
        </>
      ) : null}
    </div>
  );
}
