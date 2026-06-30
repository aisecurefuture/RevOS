"use client";

import { useCallback, useEffect, useState } from "react";

import { PageHeader } from "@/components/PageHeader";
import { Button } from "@/components/ui/Button";
import { Card } from "@/components/ui/Card";
import { Spinner } from "@/components/ui/Spinner";
import { ApiError } from "@/lib/api";
import { useBrand } from "@/lib/brand";
import { leadsApi } from "@/lib/resources";
import type { ConsentStatus, Lead } from "@/lib/types";

const CONSENT_STYLES: Record<ConsentStatus, string> = {
  confirmed: "bg-green-100 text-green-700",
  pending_double_optin: "bg-amber-100 text-amber-700",
  single_optin: "bg-blue-100 text-blue-700",
  none: "bg-slate-100 text-slate-500",
  unsubscribed: "bg-red-100 text-red-700",
};

export default function LeadsPage() {
  const { selectedBrandId } = useBrand();
  const [leads, setLeads] = useState<Lead[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [consent, setConsent] = useState("");
  const [search, setSearch] = useState("");

  const filters = useCallback(() => {
    const p: Record<string, string> = {};
    if (selectedBrandId) p.brand_id = selectedBrandId;
    if (consent) p.consent_status = consent;
    if (search) p.search = search;
    return p;
  }, [selectedBrandId, consent, search]);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      setLeads(await leadsApi.list(filters()));
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Failed to load leads");
    } finally {
      setLoading(false);
    }
  }, [filters]);

  useEffect(() => {
    void load();
  }, [load]);

  return (
    <>
      <PageHeader
        title="Leads"
        description="Permission-based — only confirmed opt-ins are mailable."
        actions={
          <Button variant="secondary" onClick={() => void leadsApi.exportCsv(filters())}>
            Export CSV
          </Button>
        }
      />

      {error ? (
        <div className="mb-4 rounded-lg bg-red-50 px-3 py-2 text-sm text-red-700">{error}</div>
      ) : null}

      <Card className="mb-4">
        <div className="flex flex-wrap items-end gap-3">
          <div>
            <label className="mb-1 block text-xs font-medium text-slate-500">Consent</label>
            <select
              value={consent}
              onChange={(e) => setConsent(e.target.value)}
              className="rounded-lg border border-slate-300 px-3 py-2 text-sm focus:border-brand focus:outline-none"
            >
              <option value="">Any</option>
              <option value="confirmed">Confirmed</option>
              <option value="pending_double_optin">Pending</option>
              <option value="unsubscribed">Unsubscribed</option>
              <option value="none">None</option>
            </select>
          </div>
          <div className="grow">
            <label className="mb-1 block text-xs font-medium text-slate-500">Search email</label>
            <input
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              placeholder="name@company.com"
              className="w-full rounded-lg border border-slate-300 px-3 py-2 text-sm focus:border-brand focus:outline-none focus:ring-1 focus:ring-brand"
            />
          </div>
          <Button variant="secondary" onClick={() => void load()}>
            Apply
          </Button>
        </div>
      </Card>

      {loading ? (
        <Spinner />
      ) : (
        <Card className="overflow-x-auto p-0">
          <table className="w-full text-sm">
            <thead className="border-b border-slate-200 text-left text-xs uppercase text-slate-400">
              <tr>
                <th className="px-4 py-3">Email</th>
                <th className="px-4 py-3">Name</th>
                <th className="px-4 py-3">Consent</th>
                <th className="px-4 py-3">Source</th>
                <th className="px-4 py-3">Score</th>
              </tr>
            </thead>
            <tbody>
              {leads.length === 0 ? (
                <tr>
                  <td colSpan={5} className="px-4 py-6 text-center text-slate-400">
                    No leads yet.
                  </td>
                </tr>
              ) : (
                leads.map((l) => (
                  <tr key={l.id} className="border-b border-slate-100 last:border-0">
                    <td className="px-4 py-3 font-medium text-slate-800">{l.email}</td>
                    <td className="px-4 py-3 text-slate-500">
                      {[l.first_name, l.last_name].filter(Boolean).join(" ") || "—"}
                    </td>
                    <td className="px-4 py-3">
                      <span
                        className={`rounded-full px-2 py-0.5 text-xs font-medium ${CONSENT_STYLES[l.consent_status]}`}
                      >
                        {l.consent_status.replace(/_/g, " ")}
                      </span>
                    </td>
                    <td className="px-4 py-3 text-slate-500">{l.source || "—"}</td>
                    <td className="px-4 py-3 text-slate-500">{l.lead_score}</td>
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
