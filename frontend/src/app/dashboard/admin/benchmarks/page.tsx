"use client";

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";

import { PageHeader } from "@/components/PageHeader";
import { Button } from "@/components/ui/Button";
import { Card, CardTitle } from "@/components/ui/Card";
import { Spinner } from "@/components/ui/Spinner";
import {
  ApiError,
  benchmarksApi,
  type BenchmarkExtractRow,
  type IndustryBenchmarkRow,
} from "@/lib/api";
import { CATEGORY_LABELS, type IndustryCategory } from "@/lib/industries";

const CATEGORIES = Object.keys(CATEGORY_LABELS).filter((c) => c !== "other") as IndustryCategory[];
const PLATFORMS = ["all", "instagram", "facebook", "tiktok", "youtube", "twitter", "linkedin", "threads"];
const inp = "rounded-lg border border-slate-300 px-3 py-2 text-sm";

function fmtPct(v: number): string {
  return `${(v * 100).toFixed(2)}%`;
}

export default function BenchmarksAdminPage() {
  const [rows, setRows] = useState<IndustryBenchmarkRow[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      setRows(await benchmarksApi.list());
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Failed to load benchmarks");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { void load(); }, [load]);

  async function remove(id: string) {
    if (!confirm("Delete this benchmark figure?")) return;
    try {
      await benchmarksApi.remove(id);
      setNotice("Deleted.");
      await load();
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Failed to delete");
    }
  }

  return (
    <>
      <PageHeader
        title="Industry Benchmarks"
        description="Admin-curated figures from published reports (Rival IQ/Quid, Socialinsider) — the fallback when RevOS's own creator cohort is too thin."
        actions={
          <Link href="/dashboard/admin" className="text-sm text-brand hover:underline">
            ← Back to admin
          </Link>
        }
      />

      {error ? <div className="mb-4 rounded-lg bg-red-50 px-3 py-2 text-sm text-red-700">{error}</div> : null}
      {notice ? <div className="mb-4 rounded-lg bg-green-50 px-3 py-2 text-sm text-green-700">{notice}</div> : null}

      <PasteAndParse onSaved={() => { setNotice("Benchmarks saved."); void load(); }} setError={setError} />

      <ManualAddForm onCreated={() => { setNotice("Benchmark added."); void load(); }} setError={setError} />

      <Card>
        <CardTitle>Current figures</CardTitle>
        {loading ? (
          <Spinner />
        ) : rows.length === 0 ? (
          <p className="text-sm text-slate-400">No benchmarks yet — add one manually or paste a report below.</p>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead className="border-b border-slate-200 text-left text-xs uppercase text-slate-400">
                <tr>
                  <th className="px-2 py-2">Industry</th>
                  <th className="px-2 py-2">Platform</th>
                  <th className="px-2 py-2">Metric</th>
                  <th className="px-2 py-2">Value</th>
                  <th className="px-2 py-2">Source</th>
                  <th className="px-2 py-2">Period</th>
                  <th className="px-2 py-2" />
                </tr>
              </thead>
              <tbody>
                {rows.map((r) => (
                  <tr key={r.id} className="border-b border-slate-100 last:border-0">
                    <td className="px-2 py-2 capitalize">{r.industry_category.replace(/_/g, " ")}</td>
                    <td className="px-2 py-2 capitalize">{r.platform}</td>
                    <td className="px-2 py-2">{r.metric}</td>
                    <td className="px-2 py-2 font-medium">{fmtPct(r.value)}</td>
                    <td className="px-2 py-2 text-slate-500">
                      {r.source_url ? (
                        <a href={r.source_url} target="_blank" rel="noreferrer" className="text-brand hover:underline">
                          {r.source}
                        </a>
                      ) : r.source}
                    </td>
                    <td className="px-2 py-2 text-slate-500">{r.period_label}</td>
                    <td className="px-2 py-2 text-right">
                      <button onClick={() => void remove(r.id)} className="text-xs text-red-500 hover:underline">
                        Delete
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Card>
    </>
  );
}

function ManualAddForm({
  onCreated, setError,
}: { onCreated: () => void; setError: (e: string | null) => void }) {
  const [category, setCategory] = useState<IndustryCategory>(CATEGORIES[0]);
  const [platform, setPlatform] = useState("all");
  const [valuePct, setValuePct] = useState("");
  const [source, setSource] = useState("");
  const [sourceUrl, setSourceUrl] = useState("");
  const [period, setPeriod] = useState("");
  const [saving, setSaving] = useState(false);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    const value = parseFloat(valuePct) / 100;
    if (!Number.isFinite(value) || value < 0 || value > 1 || !source.trim() || !period.trim()) return;
    setSaving(true);
    setError(null);
    try {
      await benchmarksApi.create({
        industry_category: category, platform, metric: "engagement_rate", value,
        source: source.trim(), source_url: sourceUrl.trim() || undefined, period_label: period.trim(),
      });
      setValuePct("");
      onCreated();
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Failed to save");
    } finally {
      setSaving(false);
    }
  }

  return (
    <Card className="mb-4">
      <CardTitle>Add manually</CardTitle>
      <form onSubmit={submit} className="grid grid-cols-2 gap-3 sm:grid-cols-4">
        <select value={category} onChange={(e) => setCategory(e.target.value as IndustryCategory)} className={inp}>
          {CATEGORIES.map((c) => (
            <option key={c} value={c}>{CATEGORY_LABELS[c]}</option>
          ))}
        </select>
        <select value={platform} onChange={(e) => setPlatform(e.target.value)} className={`${inp} capitalize`}>
          {PLATFORMS.map((p) => <option key={p} value={p}>{p}</option>)}
        </select>
        <input
          type="number" step="0.01" min={0} max={100} value={valuePct}
          onChange={(e) => setValuePct(e.target.value)} placeholder="Engagement % e.g. 2.1"
          className={inp}
        />
        <input value={period} onChange={(e) => setPeriod(e.target.value)} placeholder="Period, e.g. 2026 Annual" className={inp} />
        <input value={source} onChange={(e) => setSource(e.target.value)} placeholder="Source, e.g. Quid 2026 Report" className={`${inp} col-span-2`} />
        <input value={sourceUrl} onChange={(e) => setSourceUrl(e.target.value)} placeholder="Source URL (optional)" className={`${inp} col-span-2`} />
        <div className="col-span-2 sm:col-span-4">
          <Button type="submit" disabled={saving}>{saving ? "Saving…" : "Add benchmark"}</Button>
        </div>
      </form>
    </Card>
  );
}

function PasteAndParse({
  onSaved, setError,
}: { onSaved: () => void; setError: (e: string | null) => void }) {
  const [text, setText] = useState("");
  const [source, setSource] = useState("");
  const [sourceUrl, setSourceUrl] = useState("");
  const [period, setPeriod] = useState("");
  const [draft, setDraft] = useState<BenchmarkExtractRow[] | null>(null);
  const [note, setNote] = useState<string | null>(null);
  const [extracting, setExtracting] = useState(false);
  const [saving, setSaving] = useState(false);

  async function extract() {
    if (!text.trim() || !source.trim() || !period.trim()) return;
    setExtracting(true);
    setError(null);
    setDraft(null);
    try {
      const result = await benchmarksApi.extract(text, source.trim(), sourceUrl.trim() || undefined, period.trim());
      setDraft(result.rows);
      setNote(result.unparsed_note);
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Extraction failed");
    } finally {
      setExtracting(false);
    }
  }

  function updateRow(i: number, patch: Partial<BenchmarkExtractRow>) {
    setDraft((prev) => prev?.map((r, idx) => (idx === i ? { ...r, ...patch } : r)) ?? null);
  }

  function removeRow(i: number) {
    setDraft((prev) => prev?.filter((_, idx) => idx !== i) ?? null);
  }

  async function save() {
    if (!draft || draft.length === 0) return;
    setSaving(true);
    setError(null);
    try {
      const result = await benchmarksApi.bulkCreate({
        source: source.trim(), source_url: sourceUrl.trim() || undefined,
        period_label: period.trim(), rows: draft,
      });
      setDraft(null);
      setText("");
      onSaved();
      if (result.skipped.length > 0) {
        setNote(`${result.created} saved, ${result.skipped.length} were already on file and skipped.`);
      }
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Failed to save");
    } finally {
      setSaving(false);
    }
  }

  return (
    <Card className="mb-4">
      <CardTitle>Paste &amp; parse a report</CardTitle>
      <p className="mb-3 text-xs text-slate-500">
        Copy the benchmark table (or the whole page text) from{" "}
        <a href="https://www.quid.com/knowledge-hub/resource-library/blog/2026-social-media-industry-benchmark-report"
           target="_blank" rel="noreferrer" className="text-brand hover:underline">Quid&apos;s report</a>{" "}
        or{" "}
        <a href="https://www.socialinsider.io/social-media-benchmarks" target="_blank" rel="noreferrer"
           className="text-brand hover:underline">Socialinsider&apos;s benchmarks</a>, paste it below, extract a
        draft, then review before saving — nothing saves until you approve it.
      </p>
      <div className="mb-3 grid grid-cols-1 gap-3 sm:grid-cols-3">
        <input value={period} onChange={(e) => setPeriod(e.target.value)} placeholder="Period, e.g. 2026 Annual" className={inp} />
        <input value={source} onChange={(e) => setSource(e.target.value)} placeholder="Source, e.g. Quid 2026 Report" className={inp} />
        <input value={sourceUrl} onChange={(e) => setSourceUrl(e.target.value)} placeholder="Source URL (optional)" className={inp} />
      </div>
      <textarea
        value={text} onChange={(e) => setText(e.target.value)} rows={6}
        placeholder="Paste the report's benchmark table or page text here…"
        className="mb-3 w-full rounded-lg border border-slate-300 px-3 py-2 text-sm"
      />
      <Button type="button" onClick={() => void extract()} disabled={extracting || !text.trim() || !source.trim() || !period.trim()}>
        {extracting ? "Extracting…" : "Extract with AI"}
      </Button>

      {note ? <p className="mt-3 text-sm text-amber-600">{note}</p> : null}

      {draft ? (
        <div className="mt-4">
          {draft.length === 0 ? (
            <p className="text-sm text-slate-400">No rows were extracted — try pasting more of the table, or add manually above.</p>
          ) : (
            <>
              <p className="mb-2 text-xs font-medium uppercase tracking-wide text-slate-400">
                Review before saving
              </p>
              <div className="space-y-2">
                {draft.map((row, i) => (
                  <div key={i} className="flex flex-wrap items-center gap-2 rounded-lg border border-slate-200 p-2">
                    <select
                      value={row.industry_category}
                      onChange={(e) => updateRow(i, { industry_category: e.target.value })}
                      className={`${inp} py-1`}
                    >
                      {CATEGORIES.map((c) => <option key={c} value={c}>{CATEGORY_LABELS[c]}</option>)}
                    </select>
                    <select
                      value={row.platform}
                      onChange={(e) => updateRow(i, { platform: e.target.value })}
                      className={`${inp} py-1 capitalize`}
                    >
                      {PLATFORMS.map((p) => <option key={p} value={p}>{p}</option>)}
                    </select>
                    <input
                      type="number" step="0.01" value={(row.value * 100).toFixed(2)}
                      onChange={(e) => updateRow(i, { value: parseFloat(e.target.value) / 100 })}
                      className={`${inp} w-24 py-1`}
                    />
                    <span className="text-xs text-slate-400">%</span>
                    <button type="button" onClick={() => removeRow(i)} className="ml-auto text-xs text-red-500 hover:underline">
                      Remove
                    </button>
                  </div>
                ))}
              </div>
              <Button type="button" onClick={() => void save()} disabled={saving} className="mt-3">
                {saving ? "Saving…" : `Save ${draft.length} row(s)`}
              </Button>
            </>
          )}
        </div>
      ) : null}
    </Card>
  );
}
