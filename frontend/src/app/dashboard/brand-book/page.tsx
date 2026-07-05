"use client";

import { useCallback, useEffect, useState } from "react";

import { PageHeader } from "@/components/PageHeader";
import { Button } from "@/components/ui/Button";
import { Card, CardTitle } from "@/components/ui/Card";
import { Spinner } from "@/components/ui/Spinner";
import {
  ApiError,
  brandBookApi,
  type BrandBook,
  type BrandClaim,
  type BrandFact,
  type ContentCheck,
} from "@/lib/api";
import { useBrand } from "@/lib/brand";

function linesToArray(s: string): string[] {
  return s.split("\n").map((l) => l.trim()).filter(Boolean);
}

function Field({ label, hint, children }: { label: string; hint?: string; children: React.ReactNode }) {
  return (
    <div>
      <label className="mb-1 block text-sm font-medium text-slate-700">{label}</label>
      {hint ? <p className="mb-1 text-xs text-slate-400">{hint}</p> : null}
      {children}
    </div>
  );
}

const ta = "w-full rounded-lg border border-slate-300 px-3 py-2 text-sm";

export default function BrandBookPage() {
  const { brands, selectedBrandId } = useBrand();
  const [brandId, setBrandId] = useState<string | null>(null);

  const [book, setBook] = useState<BrandBook | null>(null);
  const [claims, setClaims] = useState<BrandClaim[]>([]);
  const [facts, setFacts] = useState<BrandFact[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [savedAt, setSavedAt] = useState<string | null>(null);

  // Local editable copies of list fields (as newline text).
  const [form, setForm] = useState({
    mission: "", positioning: "", elevator_pitch: "", target_summary: "",
    compliance_notes: "", key_messages: "", competitors: "",
    banned_terms: "", required_disclaimers: "",
  });

  useEffect(() => {
    setBrandId((cur) => cur ?? selectedBrandId ?? brands[0]?.id ?? null);
  }, [selectedBrandId, brands]);

  const load = useCallback(async (id: string) => {
    setLoading(true);
    setError(null);
    try {
      const [b, c, f] = await Promise.all([
        brandBookApi.get(id),
        brandBookApi.listClaims(id),
        brandBookApi.listFacts(id),
      ]);
      setBook(b);
      setClaims(c);
      setFacts(f);
      setForm({
        mission: b.mission ?? "", positioning: b.positioning ?? "",
        elevator_pitch: b.elevator_pitch ?? "", target_summary: b.target_summary ?? "",
        compliance_notes: b.compliance_notes ?? "",
        key_messages: b.key_messages.join("\n"), competitors: b.competitors.join("\n"),
        banned_terms: b.banned_terms.join("\n"), required_disclaimers: b.required_disclaimers.join("\n"),
      });
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Failed to load brand book");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    if (brandId) void load(brandId);
  }, [brandId, load]);

  async function save() {
    if (!brandId) return;
    setError(null);
    try {
      const b = await brandBookApi.update(brandId, {
        mission: form.mission || null,
        positioning: form.positioning || null,
        elevator_pitch: form.elevator_pitch || null,
        target_summary: form.target_summary || null,
        compliance_notes: form.compliance_notes || null,
        key_messages: linesToArray(form.key_messages),
        competitors: linesToArray(form.competitors),
        banned_terms: linesToArray(form.banned_terms),
        required_disclaimers: linesToArray(form.required_disclaimers),
      });
      setBook(b);
      setSavedAt(new Date().toLocaleTimeString());
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Save failed");
    }
  }

  async function togglePublish() {
    if (!brandId || !book) return;
    const b = await brandBookApi.update(brandId, { is_published: !book.is_published });
    setBook(b);
  }

  if (loading && !book) {
    return (
      <>
        <PageHeader title="Brand Book" description="The source of truth that grounds all AI content." />
        {brands.length === 0 ? (
          <Card><p className="text-sm text-slate-400">Create a brand first.</p></Card>
        ) : (
          <Spinner />
        )}
      </>
    );
  }

  return (
    <>
      <PageHeader
        title="Brand Book"
        description="The source of truth that grounds AI content — and the guardrails that keep it accurate."
      />

      <div className="mb-4 flex flex-wrap items-center gap-3">
        <select
          value={brandId ?? ""}
          onChange={(e) => setBrandId(e.target.value)}
          className="rounded-lg border border-slate-300 px-3 py-2 text-sm"
        >
          {brands.map((b) => <option key={b.id} value={b.id}>{b.name}</option>)}
        </select>
        {book ? (
          <button
            onClick={() => void togglePublish()}
            className={`rounded-full px-3 py-1 text-xs font-medium ${
              book.is_published ? "bg-green-100 text-green-700" : "bg-slate-100 text-slate-500"
            }`}
          >
            {book.is_published ? "● Published (grounds generation)" : "○ Draft — publish to activate"}
          </button>
        ) : null}
        {savedAt ? <span className="text-xs text-slate-400">Saved {savedAt}</span> : null}
      </div>

      {error ? (
        <div className="mb-4 rounded-lg bg-red-50 px-3 py-2 text-sm text-red-700">{error}</div>
      ) : null}

      <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
        {/* Core substance */}
        <Card>
          <CardTitle>Positioning & messaging</CardTitle>
          <div className="space-y-3">
            <Field label="Mission">
              <textarea rows={2} className={ta} value={form.mission}
                onChange={(e) => setForm({ ...form, mission: e.target.value })} />
            </Field>
            <Field label="Positioning" hint="What makes you different.">
              <textarea rows={2} className={ta} value={form.positioning}
                onChange={(e) => setForm({ ...form, positioning: e.target.value })} />
            </Field>
            <Field label="Elevator pitch">
              <textarea rows={2} className={ta} value={form.elevator_pitch}
                onChange={(e) => setForm({ ...form, elevator_pitch: e.target.value })} />
            </Field>
            <Field label="Target customer" hint="One-paragraph ICP summary.">
              <textarea rows={2} className={ta} value={form.target_summary}
                onChange={(e) => setForm({ ...form, target_summary: e.target.value })} />
            </Field>
            <Field label="Key messages" hint="One per line.">
              <textarea rows={3} className={ta} value={form.key_messages}
                onChange={(e) => setForm({ ...form, key_messages: e.target.value })} />
            </Field>
          </div>
        </Card>

        {/* Guardrails */}
        <Card>
          <CardTitle>Guardrails</CardTitle>
          <p className="mb-3 text-xs text-slate-400">
            These constrain every AI generation and power the accuracy checks.
          </p>
          <div className="space-y-3">
            <Field label="Banned terms" hint="One per line. Any generated content containing these is blocked.">
              <textarea rows={3} className={ta} value={form.banned_terms}
                onChange={(e) => setForm({ ...form, banned_terms: e.target.value })} />
            </Field>
            <Field label="Required disclaimers" hint="One per line. Flagged if missing from content that needs them.">
              <textarea rows={2} className={ta} value={form.required_disclaimers}
                onChange={(e) => setForm({ ...form, required_disclaimers: e.target.value })} />
            </Field>
            <Field label="Compliance notes" hint="Injected into every generation prompt.">
              <textarea rows={2} className={ta} value={form.compliance_notes}
                onChange={(e) => setForm({ ...form, compliance_notes: e.target.value })} />
            </Field>
            <Field label="Competitors" hint="One per line. The AI won't name or disparage these.">
              <textarea rows={2} className={ta} value={form.competitors}
                onChange={(e) => setForm({ ...form, competitors: e.target.value })} />
            </Field>
          </div>
        </Card>
      </div>

      <div className="mt-3">
        <Button onClick={() => void save()}>Save brand book</Button>
      </div>

      {brandId ? (
        <div className="mt-4 grid grid-cols-1 gap-4 lg:grid-cols-2">
          <ClaimsCard brandId={brandId} claims={claims} onChange={() => void load(brandId)} />
          <FactsCard brandId={brandId} facts={facts} onChange={() => void load(brandId)} />
        </div>
      ) : null}

      {brandId ? <CheckerCard brandId={brandId} /> : null}
    </>
  );
}

function ClaimsCard({ brandId, claims, onChange }: { brandId: string; claims: BrandClaim[]; onChange: () => void }) {
  const [claim, setClaim] = useState("");
  const [proof, setProof] = useState("");
  const [category, setCategory] = useState("metric");
  const [busy, setBusy] = useState(false);

  async function add() {
    if (!claim.trim()) return;
    setBusy(true);
    try {
      await brandBookApi.addClaim(brandId, { claim, proof: proof || undefined, category });
      setClaim(""); setProof("");
      onChange();
    } finally {
      setBusy(false);
    }
  }

  return (
    <Card>
      <CardTitle>Approved claims</CardTitle>
      <p className="mb-3 text-xs text-slate-400">
        The only factual claims the AI may make. Invented stats not backed here get flagged.
      </p>
      <div className="mb-3 space-y-2">
        <input className={ta} placeholder="e.g. Trusted by 10,000 teams" value={claim}
          onChange={(e) => setClaim(e.target.value)} />
        <div className="flex gap-2">
          <input className={`${ta} grow`} placeholder="Proof / source (optional)" value={proof}
            onChange={(e) => setProof(e.target.value)} />
          <select className={ta} value={category} onChange={(e) => setCategory(e.target.value)}>
            {["metric", "certification", "feature", "testimonial", "award", "partnership", "other"].map((c) => (
              <option key={c} value={c}>{c}</option>
            ))}
          </select>
          <Button onClick={() => void add()} disabled={busy}>Add</Button>
        </div>
      </div>
      <ul className="divide-y divide-slate-100">
        {claims.length === 0 ? <li className="py-2 text-sm text-slate-400">No claims yet.</li> : null}
        {claims.map((c) => (
          <li key={c.id} className="flex items-start justify-between gap-2 py-2 text-sm">
            <div>
              <span className="text-slate-700">{c.claim}</span>
              <span className="ml-2 rounded-full bg-slate-100 px-2 py-0.5 text-xs text-slate-500">{c.category}</span>
              {c.proof ? <p className="text-xs text-slate-400">proof: {c.proof}</p> : null}
            </div>
            <button className="text-xs text-slate-400 hover:text-red-600"
              onClick={() => brandBookApi.deleteClaim(brandId, c.id).then(onChange)}>Remove</button>
          </li>
        ))}
      </ul>
    </Card>
  );
}

function FactsCard({ brandId, facts, onChange }: { brandId: string; facts: BrandFact[]; onChange: () => void }) {
  const [topic, setTopic] = useState("");
  const [content, setContent] = useState("");
  const [busy, setBusy] = useState(false);

  async function add() {
    if (!topic.trim() || !content.trim()) return;
    setBusy(true);
    try {
      await brandBookApi.addFact(brandId, { topic, content });
      setTopic(""); setContent("");
      onChange();
    } finally {
      setBusy(false);
    }
  }

  return (
    <Card>
      <CardTitle>Knowledge base</CardTitle>
      <p className="mb-3 text-xs text-slate-400">Facts the AI can ground on (policies, specs, FAQs).</p>
      <div className="mb-3 space-y-2">
        <input className={ta} placeholder="Topic (e.g. Refund policy)" value={topic}
          onChange={(e) => setTopic(e.target.value)} />
        <div className="flex gap-2">
          <input className={`${ta} grow`} placeholder="The fact / answer" value={content}
            onChange={(e) => setContent(e.target.value)} />
          <Button onClick={() => void add()} disabled={busy}>Add</Button>
        </div>
      </div>
      <ul className="divide-y divide-slate-100">
        {facts.length === 0 ? <li className="py-2 text-sm text-slate-400">No facts yet.</li> : null}
        {facts.map((f) => (
          <li key={f.id} className="flex items-start justify-between gap-2 py-2 text-sm">
            <div>
              <span className="font-medium text-slate-700">{f.topic}</span>
              <p className="text-xs text-slate-500">{f.content}</p>
            </div>
            <button className="text-xs text-slate-400 hover:text-red-600"
              onClick={() => brandBookApi.deleteFact(brandId, f.id).then(onChange)}>Remove</button>
          </li>
        ))}
      </ul>
    </Card>
  );
}

function CheckerCard({ brandId }: { brandId: string }) {
  const [text, setText] = useState("");
  const [result, setResult] = useState<ContentCheck | null>(null);
  const [busy, setBusy] = useState(false);

  async function run() {
    setBusy(true);
    try {
      setResult(await brandBookApi.check(brandId, text));
    } finally {
      setBusy(false);
    }
  }

  return (
    <Card className="mt-4">
      <CardTitle>Accuracy check</CardTitle>
      <p className="mb-3 text-xs text-slate-400">
        Paste any content to run the same guardrail gate the autopilot uses.
      </p>
      <textarea rows={3} className={ta} value={text} onChange={(e) => setText(e.target.value)}
        placeholder="Paste a caption, script, or email…" />
      <Button className="mt-2" onClick={() => void run()} disabled={busy || !text.trim()}>
        {busy ? "Checking…" : "Check content"}
      </Button>
      {result ? (
        <div className={`mt-3 rounded-lg border px-3 py-2 text-sm ${
          result.blocked ? "border-red-200 bg-red-50"
            : result.passed ? "border-green-200 bg-green-50" : "border-amber-200 bg-amber-50"
        }`}>
          <p className="font-medium">
            {result.blocked ? "❌ Blocked" : result.passed ? "✓ Clean" : "⚠️ Needs review"}
          </p>
          {result.banned_hits.length ? (
            <p className="mt-1 text-xs text-red-700">Banned terms: {result.banned_hits.join(", ")}</p>
          ) : null}
          {result.unverified_numbers.length ? (
            <p className="mt-1 text-xs text-amber-700">
              Unverified numbers (not in approved claims): {result.unverified_numbers.join(", ")}
            </p>
          ) : null}
          {result.missing_disclaimers.length ? (
            <p className="mt-1 text-xs text-amber-700">Missing disclaimers: {result.missing_disclaimers.join(", ")}</p>
          ) : null}
        </div>
      ) : null}
    </Card>
  );
}
