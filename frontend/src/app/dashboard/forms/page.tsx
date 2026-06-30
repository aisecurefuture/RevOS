"use client";

import { useCallback, useEffect, useState } from "react";

import { PageHeader } from "@/components/PageHeader";
import { Button } from "@/components/ui/Button";
import { Card } from "@/components/ui/Card";
import { Spinner } from "@/components/ui/Spinner";
import { ApiError } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { useBrand } from "@/lib/brand";
import { formsApi } from "@/lib/resources";
import type { Form } from "@/lib/types";

const FORM_TYPES = [
  "newsletter",
  "contact",
  "consultation",
  "preorder",
  "download_gate",
  "lead_magnet",
  "waitlist",
];

export default function FormsPage() {
  const { user } = useAuth();
  const { selectedBrandId, brands } = useBrand();
  const canEdit = user ? user.role !== "viewer" : false;

  const [items, setItems] = useState<Form[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [name, setName] = useState("");
  const [formType, setFormType] = useState("newsletter");
  const [doubleOptin, setDoubleOptin] = useState(true);
  const [saving, setSaving] = useState(false);
  const [origin, setOrigin] = useState("");

  useEffect(() => setOrigin(window.location.origin), []);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      setItems(await formsApi.list(selectedBrandId));
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Failed to load forms");
    } finally {
      setLoading(false);
    }
  }, [selectedBrandId]);

  useEffect(() => {
    void load();
  }, [load]);

  async function create(e: React.FormEvent) {
    e.preventDefault();
    if (!selectedBrandId) return;
    setError(null);
    setSaving(true);
    try {
      await formsApi.create({
        brand_id: selectedBrandId,
        name,
        form_type: formType,
        double_optin: doubleOptin,
        consent_required: true,
      });
      setName("");
      await load();
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Failed to create form");
    } finally {
      setSaving(false);
    }
  }

  function embedSnippet(slug: string): string {
    return `<iframe src="${origin}/api/public/forms/${slug}" width="100%" height="420" frameborder="0"></iframe>`;
  }

  return (
    <>
      <PageHeader
        title="Forms"
        description="Embeddable, consent-first lead capture forms with optional double opt-in."
      />

      {error ? (
        <div className="mb-4 rounded-lg bg-red-50 px-3 py-2 text-sm text-red-700">{error}</div>
      ) : null}

      {canEdit ? (
        <Card className="mb-6">
          {selectedBrandId ? (
            <form onSubmit={create} className="flex flex-wrap items-end gap-3">
              <div className="grow">
                <label className="mb-1 block text-xs font-medium text-slate-500">Form name</label>
                <input
                  required
                  value={name}
                  onChange={(e) => setName(e.target.value)}
                  placeholder="Newsletter signup"
                  className="w-full rounded-lg border border-slate-300 px-3 py-2 text-sm focus:border-brand focus:outline-none focus:ring-1 focus:ring-brand"
                />
              </div>
              <div>
                <label className="mb-1 block text-xs font-medium text-slate-500">Type</label>
                <select
                  value={formType}
                  onChange={(e) => setFormType(e.target.value)}
                  className="rounded-lg border border-slate-300 px-3 py-2 text-sm focus:border-brand focus:outline-none"
                >
                  {FORM_TYPES.map((t) => (
                    <option key={t} value={t}>
                      {t.replace(/_/g, " ")}
                    </option>
                  ))}
                </select>
              </div>
              <label className="flex items-center gap-2 pb-2 text-sm text-slate-600">
                <input
                  type="checkbox"
                  checked={doubleOptin}
                  onChange={(e) => setDoubleOptin(e.target.checked)}
                />
                Double opt-in
              </label>
              <Button type="submit" disabled={saving}>
                {saving ? "Adding…" : "Add form"}
              </Button>
            </form>
          ) : (
            <p className="text-sm text-slate-500">
              Select a specific brand in the top bar to create a form
              {brands.length === 0 ? " (add a brand first)" : ""}.
            </p>
          )}
        </Card>
      ) : null}

      {loading ? (
        <Spinner />
      ) : items.length === 0 ? (
        <Card>
          <p className="text-sm text-slate-400">No forms yet.</p>
        </Card>
      ) : (
        <div className="space-y-4">
          {items.map((f) => (
            <Card key={f.id}>
              <div className="flex flex-wrap items-center justify-between gap-2">
                <div>
                  <p className="font-medium text-slate-800">{f.name}</p>
                  <p className="text-xs text-slate-400">
                    {f.form_type.replace(/_/g, " ")} · {f.double_optin ? "double" : "single"} opt-in
                  </p>
                </div>
                {canEdit ? (
                  <Button variant="ghost" onClick={() => void formsApi.remove(f.id).then(load)}>
                    Delete
                  </Button>
                ) : null}
              </div>
              <label className="mb-1 mt-3 block text-xs font-medium text-slate-500">
                Embed snippet
              </label>
              <code className="block overflow-x-auto rounded-lg bg-slate-50 p-3 text-xs text-slate-600">
                {embedSnippet(f.slug)}
              </code>
            </Card>
          ))}
        </div>
      )}
    </>
  );
}
