"use client";

import { useCallback, useEffect, useRef, useState } from "react";

import { AddLeadModal } from "@/components/AddLeadModal";
import { PageHeader } from "@/components/PageHeader";
import { Button } from "@/components/ui/Button";
import { Card } from "@/components/ui/Card";
import { Spinner } from "@/components/ui/Spinner";
import { ApiError } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { useBrand } from "@/lib/brand";
import { contactsApi, dealsApi } from "@/lib/resources";
import type { Contact, Deal, PipelineStage } from "@/lib/types";

type Tab = "contacts" | "pipeline";

export default function CrmPage() {
  const { user } = useAuth();
  const { selectedBrandId } = useBrand();
  const canEdit = user ? user.role !== "viewer" : false;

  const [tab, setTab] = useState<Tab>("contacts");
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  return (
    <>
      <PageHeader
        title="CRM"
        description="Contacts, companies, deals & pipeline — your sales network in one place."
      />

      <div className="mb-4 flex gap-2">
        {(["contacts", "pipeline"] as Tab[]).map((t) => (
          <button
            key={t}
            type="button"
            onClick={() => setTab(t)}
            className={`rounded-lg px-3 py-1.5 text-sm font-medium capitalize ${
              tab === t ? "bg-brand text-white" : "bg-white text-slate-600 border border-slate-200"
            }`}
          >
            {t}
          </button>
        ))}
      </div>

      {error ? (
        <div className="mb-4 rounded-lg bg-red-50 px-3 py-2 text-sm text-red-700">{error}</div>
      ) : null}
      {notice ? (
        <div className="mb-4 rounded-lg bg-green-50 px-3 py-2 text-sm text-green-700">{notice}</div>
      ) : null}

      {tab === "contacts" ? (
        <Contacts
          brandId={selectedBrandId}
          canEdit={canEdit}
          setError={setError}
          setNotice={setNotice}
        />
      ) : (
        <Pipeline brandId={selectedBrandId} canEdit={canEdit} setError={setError} />
      )}
    </>
  );
}

function Contacts({
  brandId,
  canEdit,
  setError,
  setNotice,
}: {
  brandId: string | null;
  canEdit: boolean;
  setError: (s: string | null) => void;
  setNotice: (s: string | null) => void;
}) {
  const [contacts, setContacts] = useState<Contact[]>([]);
  const [loading, setLoading] = useState(true);
  const [search, setSearch] = useState("");
  const [showAdd, setShowAdd] = useState(false);
  const fileRef = useRef<HTMLInputElement>(null);

  const params = useCallback(() => {
    const p: Record<string, string> = {};
    if (brandId) p.brand_id = brandId;
    if (search) p.search = search;
    return p;
  }, [brandId, search]);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      setContacts(await contactsApi.list(params()));
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Failed to load contacts");
    } finally {
      setLoading(false);
    }
  }, [params, setError]);

  useEffect(() => {
    void load();
  }, [load]);

  async function onImport(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0];
    if (!file) return;
    setError(null);
    try {
      const r = await contactsApi.importCsv(file, brandId);
      setNotice(
        `Imported ${r.created} new contacts, updated ${r.updated}, ${r.companies_created} companies. ${r.note}`,
      );
      await load();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Import failed");
    } finally {
      if (fileRef.current) fileRef.current.value = "";
    }
  }

  return (
    <>
      <Card className="mb-4">
        <div className="flex flex-wrap items-end gap-3">
          <div className="grow">
            <label className="mb-1 block text-xs font-medium text-slate-500">Search</label>
            <input
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              placeholder="Name or email"
              className="w-full rounded-lg border border-slate-300 px-3 py-2 text-sm focus:border-brand focus:outline-none focus:ring-1 focus:ring-brand"
            />
          </div>
          <Button variant="secondary" onClick={() => void load()}>
            Apply
          </Button>
          <Button variant="secondary" onClick={() => void contactsApi.exportCsv(params())}>
            Export
          </Button>
          {canEdit ? (
            <>
              <input
                ref={fileRef}
                type="file"
                accept=".csv"
                onChange={onImport}
                className="hidden"
              />
              <Button onClick={() => fileRef.current?.click()}>Import LinkedIn CSV</Button>
              <Button onClick={() => setShowAdd(true)}>Add contact</Button>
            </>
          ) : null}
        </div>
      </Card>

      <AddLeadModal
        open={showAdd}
        variant="contact"
        brandId={brandId}
        onClose={() => setShowAdd(false)}
        onCreated={() => void load()}
      />

      {loading ? (
        <Spinner />
      ) : (
        <Card className="overflow-x-auto p-0">
          <table className="w-full text-sm">
            <thead className="border-b border-slate-200 text-left text-xs uppercase text-slate-400">
              <tr>
                <th className="px-4 py-3">Name</th>
                <th className="px-4 py-3">Email</th>
                <th className="px-4 py-3">Title</th>
                <th className="px-4 py-3">Source</th>
                <th className="px-4 py-3">Score</th>
              </tr>
            </thead>
            <tbody>
              {contacts.length === 0 ? (
                <tr>
                  <td colSpan={5} className="px-4 py-6 text-center text-slate-400">
                    No contacts yet — import your LinkedIn export to get started.
                  </td>
                </tr>
              ) : (
                contacts.map((c) => (
                  <tr key={c.id} className="border-b border-slate-100 last:border-0">
                    <td className="px-4 py-3 font-medium text-slate-800">
                      {[c.first_name, c.last_name].filter(Boolean).join(" ") || "—"}
                    </td>
                    <td className="px-4 py-3 text-slate-500">{c.email || "—"}</td>
                    <td className="px-4 py-3 text-slate-500">{c.title || "—"}</td>
                    <td className="px-4 py-3 text-slate-400">{c.source || "—"}</td>
                    <td className="px-4 py-3 font-medium text-slate-700">{c.lead_score}</td>
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

function Pipeline({
  brandId,
  canEdit,
  setError,
}: {
  brandId: string | null;
  canEdit: boolean;
  setError: (s: string | null) => void;
}) {
  const [stages, setStages] = useState<PipelineStage[]>([]);
  const [deals, setDeals] = useState<Deal[]>([]);
  const [loading, setLoading] = useState(true);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const [s, d] = await Promise.all([
        dealsApi.pipeline(brandId),
        dealsApi.list(brandId),
      ]);
      setStages(s);
      setDeals(d);
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Failed to load pipeline");
    } finally {
      setLoading(false);
    }
  }, [brandId, setError]);

  useEffect(() => {
    void load();
  }, [load]);

  async function move(deal: Deal, stageId: string) {
    try {
      await dealsApi.move(deal.id, stageId);
      await load();
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Move failed");
    }
  }

  if (loading) return <Spinner />;

  return (
    <div className="flex gap-4 overflow-x-auto pb-2">
      {stages.map((stage) => {
        const stageDeals = deals.filter((d) => d.pipeline_stage_id === stage.id);
        return (
          <div key={stage.id} className="w-64 shrink-0">
            <div className="mb-2 flex items-center justify-between">
              <span className="text-sm font-semibold text-slate-700">{stage.name}</span>
              <span className="text-xs text-slate-400">{stageDeals.length}</span>
            </div>
            <div className="space-y-2">
              {stageDeals.map((d) => (
                <Card key={d.id} className="p-3">
                  <p className="text-sm font-medium text-slate-800">{d.name}</p>
                  {d.amount_cents != null ? (
                    <p className="text-xs text-slate-500">
                      ${(d.amount_cents / 100).toLocaleString()}
                    </p>
                  ) : null}
                  {canEdit ? (
                    <select
                      value={stage.id}
                      onChange={(e) => void move(d, e.target.value)}
                      className="mt-2 w-full rounded border border-slate-200 px-2 py-1 text-xs"
                    >
                      {stages.map((s) => (
                        <option key={s.id} value={s.id}>
                          {s.name}
                        </option>
                      ))}
                    </select>
                  ) : null}
                </Card>
              ))}
            </div>
          </div>
        );
      })}
    </div>
  );
}
