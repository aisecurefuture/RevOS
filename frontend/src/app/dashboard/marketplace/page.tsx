"use client";

import { useState } from "react";

import { PageHeader } from "@/components/PageHeader";

import { DiscoverTab } from "./DiscoverTab";
import { InsightsTab } from "./InsightsTab";
import { RequestsTab } from "./RequestsTab";
import { RosterTab } from "./RosterTab";

type Tab = "discover" | "requests" | "roster" | "insights";

const TABS: { key: Tab; label: string }[] = [
  { key: "discover", label: "Discover" },
  { key: "requests", label: "Requests" },
  { key: "roster", label: "My roster" },
  { key: "insights", label: "Insights" },
];

export default function MarketplacePage() {
  const [tab, setTab] = useState<Tab>("discover");
  const [notice, setNotice] = useState<string | null>(null);

  return (
    <>
      <PageHeader
        title="Marketplace"
        description="Discover the right partners and reach out. Consent-first — only opted-in profiles appear, and contact details stay private until a request is accepted."
      />

      {notice ? (
        <div className="mb-4 rounded-lg bg-green-50 px-3 py-2 text-sm text-green-700">{notice}</div>
      ) : null}

      <div className="mb-4 flex gap-2 border-b border-slate-200">
        {TABS.map((t) => (
          <button
            key={t.key}
            type="button"
            onClick={() => setTab(t.key)}
            className={`-mb-px border-b-2 px-3 py-2 text-sm font-medium ${
              tab === t.key
                ? "border-brand text-brand"
                : "border-transparent text-slate-500 hover:text-slate-700"
            }`}
          >
            {t.label}
          </button>
        ))}
      </div>

      {tab === "discover" ? <DiscoverTab setNotice={setNotice} /> : null}
      {tab === "requests" ? <RequestsTab setNotice={setNotice} /> : null}
      {tab === "roster" ? <RosterTab setNotice={setNotice} /> : null}
      {tab === "insights" ? <InsightsTab /> : null}
    </>
  );
}
