"use client";

import { useCallback, useEffect, useState } from "react";

import { NoBrandCta } from "@/components/NoBrandCta";
import { PageHeader } from "@/components/PageHeader";
import { Button } from "@/components/ui/Button";
import { Card, CardTitle } from "@/components/ui/Card";
import { Spinner } from "@/components/ui/Spinner";
import {
  ApiError,
  autopilotApi,
  BRAND_ARCHETYPES,
  brandBookApi,
  type AutopilotConfig,
  type AutopilotRun,
  type BrandBook,
  type BrandClaim,
  type BrandFact,
  type ContentCheck,
  type CoreValue,
  type VoiceSpectrum,
} from "@/lib/api";
import { useAuth } from "@/lib/auth";
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
    mission: "", vision: "", positioning: "", elevator_pitch: "", target_summary: "",
    audience_exclusions: "", compliance_notes: "", key_messages: "", competitors: "",
    banned_terms: "", required_disclaimers: "", brand_story: "",
  });
  const [coreValues, setCoreValues] = useState<CoreValue[]>([]);
  const [archetype, setArchetype] = useState("");
  const [spectrum, setSpectrum] = useState<VoiceSpectrum>({});

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
        mission: b.mission ?? "", vision: b.vision ?? "", positioning: b.positioning ?? "",
        elevator_pitch: b.elevator_pitch ?? "", target_summary: b.target_summary ?? "",
        audience_exclusions: b.audience_exclusions ?? "",
        compliance_notes: b.compliance_notes ?? "",
        key_messages: b.key_messages.join("\n"), competitors: b.competitors.join("\n"),
        banned_terms: b.banned_terms.join("\n"), required_disclaimers: b.required_disclaimers.join("\n"),
        brand_story: b.brand_story ?? "",
      });
      setCoreValues(b.core_values.length ? b.core_values : []);
      setArchetype(b.brand_archetype ?? "");
      setSpectrum(b.voice_spectrum ?? {});
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
        vision: form.vision || null,
        positioning: form.positioning || null,
        elevator_pitch: form.elevator_pitch || null,
        target_summary: form.target_summary || null,
        audience_exclusions: form.audience_exclusions || null,
        compliance_notes: form.compliance_notes || null,
        key_messages: linesToArray(form.key_messages),
        competitors: linesToArray(form.competitors),
        banned_terms: linesToArray(form.banned_terms),
        required_disclaimers: linesToArray(form.required_disclaimers),
        brand_story: form.brand_story || null,
        core_values: coreValues.filter((cv) => cv.value.trim()),
        brand_archetype: archetype || null,
        voice_spectrum: spectrum,
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
          <NoBrandCta feature="The Brand Book" />
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
            <Field label="Mission" hint="Your purpose, present tense. What do you do, for whom, and why?">
              <textarea rows={2} className={ta} value={form.mission}
                onChange={(e) => setForm({ ...form, mission: e.target.value })} />
            </Field>
            <Field label="Vision" hint="The future. If you accomplish this mission every day, long-term — what's the outcome, for you AND for your audience?">
              <textarea rows={2} className={ta} value={form.vision}
                onChange={(e) => setForm({ ...form, vision: e.target.value })} />
            </Field>
            <Field label="Positioning" hint="What makes you different.">
              <textarea rows={2} className={ta} value={form.positioning}
                onChange={(e) => setForm({ ...form, positioning: e.target.value })} />
            </Field>
            <Field label="Elevator pitch">
              <textarea rows={2} className={ta} value={form.elevator_pitch}
                onChange={(e) => setForm({ ...form, elevator_pitch: e.target.value })} />
            </Field>
            <Field label="Target customer" hint="One-paragraph ICP summary — demographics and personas/situations.">
              <textarea rows={2} className={ta} value={form.target_summary}
                onChange={(e) => setForm({ ...form, target_summary: e.target.value })} />
            </Field>
            <Field label="Who this is NOT for" hint="Knowing who you're for includes knowing who you aren't. Describe someone you're deliberately not making content for, and why.">
              <textarea rows={2} className={ta} value={form.audience_exclusions}
                onChange={(e) => setForm({ ...form, audience_exclusions: e.target.value })} />
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

      <div className="mt-4 grid grid-cols-1 gap-4 lg:grid-cols-2">
        <Card>
          <CardTitle>Core values</CardTitle>
          <p className="mb-3 text-xs text-slate-400">
            A value, what it means in practice, and how it shows up in your content. If a value has
            no content example, that's a content opportunity — if content doesn't reflect any value,
            it's probably off-brand.
          </p>
          <CoreValuesEditor values={coreValues} onChange={setCoreValues} />
        </Card>

        <Card>
          <CardTitle>Voice anchors</CardTitle>
          <p className="mb-3 text-xs text-slate-400">
            Cheap, consistent shorthand for tone — faster to fill out than freeform style notes.
          </p>
          <div className="space-y-3">
            <Field label="Brand archetype" hint="Which of the 12 Jungian archetypes resonates most?">
              <select className={ta} value={archetype} onChange={(e) => setArchetype(e.target.value)}>
                <option value="">— none —</option>
                {BRAND_ARCHETYPES.map((a) => (
                  <option key={a} value={a}>
                    {a.split("_").map((w) => w[0].toUpperCase() + w.slice(1)).join(" ")}
                  </option>
                ))}
              </select>
            </Field>
            <VoiceSpectrumEditor spectrum={spectrum} onChange={setSpectrum} />
          </div>
        </Card>
      </div>

      <Card className="mt-4">
        <CardTitle>Brand story</CardTitle>
        <p className="mb-3 text-xs text-slate-400">
          At the heart of content that resonates is storytelling. Use a condensed three-act
          structure — who this is about, the inciting incident that disrupted normal life, the
          obstacles faced, the lowest point, the climax, and the transformation/legacy. This is
          exactly the kind of authentic material that makes short-form avatar video land.
        </p>
        <textarea
          rows={8} className={ta} value={form.brand_story}
          onChange={(e) => setForm({ ...form, brand_story: e.target.value })}
          placeholder={
            "Who is this about?\n\nWhat was the inciting incident?\n\nWhy and how did you decide to take action?\n\n" +
            "What obstacles did you face?\n\nWhat was your lowest point after taking action?\n\n" +
            "What's the climax — the highest-stakes confrontation?\n\nWhat's the transformation / legacy?"
          }
        />
      </Card>

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
      {brandId ? <AutopilotCard brandId={brandId} /> : null}
    </>
  );
}

function CoreValuesEditor({ values, onChange }: { values: CoreValue[]; onChange: (v: CoreValue[]) => void }) {
  function update(i: number, patch: Partial<CoreValue>) {
    onChange(values.map((v, idx) => (idx === i ? { ...v, ...patch } : v)));
  }
  function remove(i: number) {
    onChange(values.filter((_, idx) => idx !== i));
  }
  return (
    <div className="space-y-3">
      {values.map((v, i) => (
        <div key={i} className="space-y-1 rounded-lg border border-slate-200 p-2">
          <div className="flex gap-2">
            <input className={`${ta} grow`} placeholder="Value (e.g. Presence)" value={v.value}
              onChange={(e) => update(i, { value: e.target.value })} />
            <button type="button" className="text-xs text-slate-400 hover:text-red-600" onClick={() => remove(i)}>
              Remove
            </button>
          </div>
          <input className={ta} placeholder="How you practice it in life" value={v.statement ?? ""}
            onChange={(e) => update(i, { statement: e.target.value })} />
          <input className={ta} placeholder="How it shows up in your content" value={v.example ?? ""}
            onChange={(e) => update(i, { example: e.target.value })} />
        </div>
      ))}
      <Button type="button" variant="secondary" onClick={() => onChange([...values, { value: "", statement: "", example: "" }])}>
        + Add value
      </Button>
    </div>
  );
}

const SPECTRUMS: { key: keyof VoiceSpectrum; lo: string; hi: string }[] = [
  { key: "humor", lo: "Funny", hi: "Serious" },
  { key: "energy", lo: "Matter-of-fact", hi: "Enthusiastic" },
  { key: "formality", lo: "Formal", hi: "Casual" },
  { key: "convention", lo: "Conventional", hi: "Quirky" },
];

function VoiceSpectrumEditor({ spectrum, onChange }: { spectrum: VoiceSpectrum; onChange: (s: VoiceSpectrum) => void }) {
  return (
    <div className="space-y-3">
      {SPECTRUMS.map(({ key, lo, hi }) => (
        <div key={key}>
          <div className="flex justify-between text-xs text-slate-500">
            <span>{lo}</span>
            <span>{hi}</span>
          </div>
          <input
            type="range" min={1} max={5} value={spectrum[key] ?? 3}
            onChange={(e) => onChange({ ...spectrum, [key]: Number(e.target.value) })}
            className="w-full"
          />
        </div>
      ))}
    </div>
  );
}

// Text platforms auto-publish a caption; media platforms (IG/YouTube/TikTok)
// need an image/video, so autopilot drafts their caption and queues it for a
// human to attach media + approve.
const TEXT_PLATFORMS: { value: string; label: string }[] = [
  { value: "facebook", label: "Facebook" },
  { value: "twitter", label: "X" },
  { value: "linkedin", label: "LinkedIn" },
  { value: "threads", label: "Threads" },
];
const MEDIA_PLATFORMS: { value: string; label: string }[] = [
  { value: "instagram", label: "Instagram" },
  { value: "youtube", label: "YouTube" },
  { value: "tiktok", label: "TikTok" },
];

function AutopilotCard({ brandId }: { brandId: string }) {
  const { user } = useAuth();
  const isAdmin = user?.role === "admin" || user?.role === "owner";

  const [cfg, setCfg] = useState<AutopilotConfig | null>(null);
  const [themes, setThemes] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [run, setRun] = useState<AutopilotRun | null>(null);

  useEffect(() => {
    if (!isAdmin) return;
    autopilotApi.get(brandId)
      .then((c) => { setCfg(c); setThemes(c.content_themes.join("\n")); })
      .catch(() => setCfg(null));
  }, [brandId, isAdmin]);

  if (!isAdmin) return null;
  if (!cfg) return null;

  function patch(data: Partial<AutopilotConfig>) {
    setCfg((c) => (c ? { ...c, ...data } : c));
  }
  function togglePlatform(p: string) {
    const has = cfg!.platforms.includes(p);
    patch({ platforms: has ? cfg!.platforms.filter((x) => x !== p) : [...cfg!.platforms, p] });
  }

  async function save() {
    setBusy(true); setError(null);
    try {
      const c = await autopilotApi.update(brandId, {
        enabled: cfg!.enabled, auto_publish: cfg!.auto_publish,
        platforms: cfg!.platforms, posts_per_run: cfg!.posts_per_run,
        run_interval_hours: cfg!.run_interval_hours, default_cta: cfg!.default_cta,
        content_themes: themes.split("\n").map((t) => t.trim()).filter(Boolean),
      });
      setCfg(c); setThemes(c.content_themes.join("\n"));
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Save failed");
    } finally {
      setBusy(false);
    }
  }

  async function runNow() {
    setBusy(true); setError(null); setRun(null);
    try {
      setRun(await autopilotApi.run(brandId));
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Run failed");
    } finally {
      setBusy(false);
    }
  }

  return (
    <Card className="mt-4">
      <CardTitle>🤖 Content autopilot</CardTitle>
      <div className="mb-3 rounded-lg border border-amber-200 bg-amber-50 px-3 py-2 text-xs text-amber-800">
        <strong>Hands-off content.</strong> Autopilot generates on-brand posts grounded in this
        book and runs them through the accuracy gate above. With auto-publish on, only content
        that passes <em>cleanly</em> is posted automatically — anything flagged (e.g. an unverified
        statistic) always waits for your review, and banned-term content is discarded. Requires a
        <strong> published</strong> book and connected accounts.
      </div>

      <div className="space-y-3">
        <label className="flex items-center gap-2 text-sm">
          <input type="checkbox" checked={cfg.enabled} onChange={(e) => patch({ enabled: e.target.checked })} />
          Enable autopilot
        </label>

        <div>
          <p className="mb-1 text-xs font-medium text-slate-500">Text platforms — auto-publish captions</p>
          <div className="flex flex-wrap gap-3">
            {TEXT_PLATFORMS.map((p) => (
              <label key={p.value} className="flex items-center gap-1 text-sm">
                <input type="checkbox" checked={cfg.platforms.includes(p.value)} onChange={() => togglePlatform(p.value)} />
                {p.label}
              </label>
            ))}
          </div>
          <p className="mb-1 mt-3 text-xs font-medium text-slate-500">Media platforms — draft caption, queue for review</p>
          <div className="flex flex-wrap gap-3">
            {MEDIA_PLATFORMS.map((p) => (
              <label key={p.value} className="flex items-center gap-1 text-sm">
                <input type="checkbox" checked={cfg.platforms.includes(p.value)} onChange={() => togglePlatform(p.value)} />
                {p.label}
              </label>
            ))}
          </div>
          <p className="mt-1 text-xs text-slate-400">
            Instagram, YouTube, and TikTok need an image or video. Autopilot writes an on-brand
            caption and queues it for you to attach media and approve — it never auto-posts them empty.
          </p>
        </div>

        <div className="flex flex-wrap gap-4 text-sm">
          <label className="flex items-center gap-2">
            Posts per run
            <input type="number" min={1} max={5} value={cfg.posts_per_run}
              onChange={(e) => patch({ posts_per_run: Number(e.target.value) })}
              className="w-16 rounded border border-slate-300 px-2 py-1" />
          </label>
          <label className="flex items-center gap-2">
            Every (hours)
            <input type="number" min={1} value={cfg.run_interval_hours}
              onChange={(e) => patch({ run_interval_hours: Number(e.target.value) })}
              className="w-20 rounded border border-slate-300 px-2 py-1" />
          </label>
        </div>

        <Field label="Content angles / themes" hint="One per line — rotated across posts.">
          <textarea rows={2} className={ta} value={themes} onChange={(e) => setThemes(e.target.value)} />
        </Field>
        <Field label="Default call to action">
          <input className={ta} value={cfg.default_cta ?? ""}
            onChange={(e) => patch({ default_cta: e.target.value })} />
        </Field>

        <label className="flex items-start gap-2 rounded-lg border border-slate-200 px-3 py-2 text-sm">
          <input type="checkbox" checked={cfg.auto_publish} className="mt-0.5"
            onChange={(e) => patch({ auto_publish: e.target.checked })} />
          <span>
            <strong>Auto-publish clean content (full hands-off)</strong>
            <span className="block text-xs text-slate-500">
              Off = every generated post is queued for your approval. On = clean posts publish
              automatically; flagged ones still wait for you.
            </span>
          </span>
        </label>

        {error ? <p className="text-xs text-red-600">{error}</p> : null}
        <div className="flex items-center gap-2">
          <Button onClick={() => void save()} disabled={busy}>Save autopilot</Button>
          <Button variant="secondary" onClick={() => void runNow()} disabled={busy}>
            {busy ? "Running…" : "Run once now"}
          </Button>
          {cfg.last_run_at ? (
            <span className="text-xs text-slate-400">
              Last run {new Date(cfg.last_run_at + "Z").toLocaleString()}
            </span>
          ) : null}
        </div>

        {run ? (
          <div className="rounded-lg bg-slate-50 border border-slate-200 px-3 py-2 text-sm text-slate-700">
            Generated {run.generated} · Published {run.published} · Queued for review {run.queued}
            {" "}· Blocked {run.blocked}
            {run.generated === 0 ? (
              <span className="block text-xs text-slate-400">
                Nothing generated — check that an AI provider is configured, the book is published,
                and a target platform is connected.
              </span>
            ) : null}
          </div>
        ) : null}
      </div>
    </Card>
  );
}

function ClaimsCard({ brandId, claims, onChange }: { brandId: string; claims: BrandClaim[]; onChange: () => void }) {
  const [claim, setClaim] = useState("");
  const [proof, setProof] = useState("");
  const [category, setCategory] = useState("metric");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function add() {
    if (!claim.trim()) return;
    setBusy(true);
    setError(null);
    try {
      await brandBookApi.addClaim(brandId, { claim, proof: proof || undefined, category });
      setClaim(""); setProof("");
      onChange();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not add claim");
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
        {error ? <p className="text-xs text-red-600">{error}</p> : null}
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
  const [error, setError] = useState<string | null>(null);

  async function add() {
    if (!topic.trim() || !content.trim()) return;
    setBusy(true);
    setError(null);
    try {
      await brandBookApi.addFact(brandId, { topic, content });
      setTopic(""); setContent("");
      onChange();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not add fact");
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
        {error ? <p className="text-xs text-red-600">{error}</p> : null}
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
  const [error, setError] = useState<string | null>(null);

  async function run() {
    setBusy(true);
    setError(null);
    try {
      setResult(await brandBookApi.check(brandId, text));
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Check failed");
    } finally {
      setBusy(false);
    }
  }

  return (
    <Card className="mt-4">
      <CardTitle>Accuracy check</CardTitle>
      <p className="mb-3 text-xs text-slate-400">
        Paste any content to run the same combined gate real generation goes through —
        banned terms, missing disclaimers, ungrounded numbers, and (if enabled) LLM claim
        verification against your approved claims and facts.
      </p>
      <textarea rows={3} className={ta} value={text} onChange={(e) => setText(e.target.value)}
        placeholder="Paste a caption, script, or email…" />
      <Button className="mt-2" onClick={() => void run()} disabled={busy || !text.trim()}>
        {busy ? "Checking…" : "Check content"}
      </Button>
      {error ? <p className="mt-2 text-xs text-red-600">{error}</p> : null}
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
          {result.unsupported_claims.length ? (
            <p className="mt-1 text-xs text-amber-700">
              Unsupported claims (not backed by your Brand Book): {result.unsupported_claims.join("; ")}
            </p>
          ) : null}
          {result.llm_error ? (
            <p className="mt-1 text-xs text-amber-700">⚠ Couldn&apos;t fully verify: {result.llm_error}</p>
          ) : null}
          {result.llm_checked ? (
            <p className="mt-1 text-xs text-slate-400">✓ AI-verified against your approved claims.</p>
          ) : null}
        </div>
      ) : null}
    </Card>
  );
}
