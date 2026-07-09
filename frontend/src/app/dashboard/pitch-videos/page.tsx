"use client";

import { useCallback, useEffect, useRef, useState } from "react";

import { PageHeader } from "@/components/PageHeader";
import { Button } from "@/components/ui/Button";
import { Card, CardTitle } from "@/components/ui/Card";
import { Spinner } from "@/components/ui/Spinner";
import { ApiError, pitchVideoApi, type PitchVideoJob } from "@/lib/api";
import { useBrand } from "@/lib/brand";

const ta = "w-full rounded-lg border border-slate-300 px-3 py-2 text-sm font-mono";

// One scene of every layout, in a sensible pitch order — doubles as living
// documentation of each layout's content shape. Kept aligned with the backend
// schema (app/schemas/pitch_video.py) and remotion/src/types.ts.
function starterDeck(brandSlug: string): string {
  return JSON.stringify(
    {
      brandId: brandSlug,
      title: "Untitled deck",
      aspectRatio: "16:9",
      voice: "",
      scenes: [
        {
          id: "hook",
          layout: "hero",
          variant: "dark",
          content: { eyebrow: "Small label above", headline: "Your headline here.", sub: "A supporting line." },
          narration: "Spoken voiceover for this scene. Its length sets the scene's duration.",
        },
        {
          id: "stats",
          layout: "stat-trio",
          variant: "dark",
          content: {
            stats: [
              { value: "3×", label: "First stat" },
              { value: "$10M", label: "Second stat" },
              { value: "#1", label: "Third stat" },
            ],
          },
          narration: "Two to four big numbers with labels.",
        },
        {
          id: "big-idea",
          layout: "statement",
          variant: "light",
          content: { text: "One bold sentence, centered." },
          narration: "A statement scene. Add an optional equation list for an A plus B equals C beat.",
        },
        {
          id: "compare",
          layout: "two-column",
          variant: "light",
          content: {
            left: { heading: "Old way", body: "What's wrong with it." },
            right: { heading: "New way", body: "Why yours wins." },
          },
          narration: "Two panes side by side.",
        },
        {
          id: "how-it-works",
          layout: "architecture",
          variant: "light",
          content: {
            bands: [
              { label: "Step one", description: "Optional description." },
              { label: "Step two", description: "Optional description." },
              { label: "Step three" },
            ],
          },
          narration: "Stacked layers connected top to bottom.",
        },
        {
          id: "growth",
          layout: "bar-chart",
          variant: "light",
          content: {
            bars: [
              { category: "2026", segments: [{ label: "Product", value: 2 }] },
              { category: "2027", segments: [{ label: "Product", value: 5 }, { label: "Services", value: 2 }] },
              { category: "2028", segments: [{ label: "Product", value: 12 }, { label: "Services", value: 4 }] },
            ],
            note: "Optional on-screen caption, e.g. 'Illustrative model — not a forecast.'",
          },
          narration: "A stacked bar chart. Segments stack per category.",
        },
        {
          id: "roadmap",
          layout: "timeline",
          variant: "light",
          content: {
            steps: [
              { label: "Q1", description: "Optional" },
              { label: "Q2" },
              { label: "Q3" },
            ],
          },
          narration: "Dots on a line, two to ten steps.",
        },
        {
          id: "team",
          layout: "team",
          variant: "light",
          content: {
            members: [
              { name: "Full Name", role: "Title", bio: "Optional one-liner." },
              { name: "Full Name", role: "Title" },
            ],
          },
          narration: "The people behind it.",
        },
        {
          id: "cta",
          layout: "close",
          variant: "dark",
          content: { headline: "Let's talk.", sub: "you@yourcompany.com · yourcompany.com" },
          narration: "Closing line. The brand wordmark appears automatically if set.",
        },
      ],
    },
    null,
    2,
  );
}

// Quick-reference rows for the format help panel.
const FORMAT_ROWS: { field: string; desc: string }[] = [
  { field: "brandId", desc: "Your brand's slug (auto-filled by the template button) — colors, fonts, and wordmark come from that brand's design tokens." },
  { field: "title", desc: "Job title shown in the list below; not rendered in the video." },
  { field: "aspectRatio", desc: '"16:9" (default), "9:16", or "1:1".' },
  { field: "voice", desc: "A stock narrator name (ask an admin for the list, e.g. \"Ana Florence\" or \"Damien Black\"). Leave \"\" to use the account default." },
  { field: "scenes[].id", desc: "Any unique name per scene." },
  { field: "scenes[].layout", desc: "hero · statement · stat-trio · two-column · architecture · bar-chart · timeline · team · close — the starter template shows one of each with its exact content shape." },
  { field: "scenes[].variant", desc: '"light" or "dark" background, per scene.' },
  { field: "scenes[].content", desc: "Layout-specific — copy the shape from the matching scene in the starter template." },
  { field: "scenes[].narration", desc: "The spoken voiceover. Each scene lasts exactly as long as its narration audio. Tip: write initialisms phonetically for the voice (\"A-I\", \"U-R-L\", \"CyberArmor dot A-I\") — on-screen text can keep normal spelling." },
];

const STATUS_LABEL: Record<string, string> = {
  queued: "Queued",
  generating_audio: "Generating narration…",
  rendering: "Rendering video…",
  succeeded: "Done",
  failed: "Failed",
  cancelled: "Cancelled",
};

export default function PitchVideoStudioPage() {
  const { brands, selectedBrandId } = useBrand();
  const [enabled, setEnabled] = useState<boolean | null>(null);
  const [deckText, setDeckText] = useState("");
  const [jobs, setJobs] = useState<PitchVideoJob[]>([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);

  const selectedBrand = brands.find((b) => b.id === selectedBrandId) ?? brands[0] ?? null;

  const loadJobs = useCallback(async () => {
    try {
      setJobs(await pitchVideoApi.listJobs());
    } catch {
      /* non-fatal — feature may be disabled */
    }
  }, []);

  useEffect(() => {
    pitchVideoApi.status().then((s) => setEnabled(s.enabled)).catch(() => setEnabled(false));
    void loadJobs();
  }, [loadJobs]);

  // Poll while any job is still in flight.
  useEffect(() => {
    if (!jobs.some((j) => ["queued", "generating_audio", "rendering"].includes(j.status))) return;
    const t = setInterval(() => void loadJobs(), 4000);
    return () => clearInterval(t);
  }, [jobs, loadJobs]);

  function loadStarterTemplate() {
    setDeckText(starterDeck(selectedBrand?.slug ?? "your-brand-slug"));
  }

  function handleFileUpload(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0];
    if (!file) return;
    const reader = new FileReader();
    reader.onload = () => setDeckText(String(reader.result ?? ""));
    reader.readAsText(file);
  }

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      const deckSpec = JSON.parse(deckText);
      await pitchVideoApi.createJob(deckSpec);
      await loadJobs();
    } catch (err) {
      if (err instanceof SyntaxError) {
        setError("That's not valid JSON — check the Deck Spec for a typo.");
      } else {
        setError(err instanceof ApiError ? err.message : "Could not start the render");
      }
    } finally {
      setBusy(false);
    }
  }

  if (enabled === null) return <Spinner />;

  if (!enabled) {
    return (
      <>
        <PageHeader title="Pitch Video Studio" description="Turn a Deck Spec into a narrated MP4." />
        <Card>
          <p className="text-sm text-slate-500">
            Pitch Video Studio isn&apos;t enabled on this deployment yet. Ask an admin to set
            <code className="mx-1 rounded bg-slate-100 px-1.5 py-0.5">PITCH_VIDEO_STUDIO_ENABLED=true</code>
            and confirm Remotion licensing (see <code>remotion/README.md</code>) before turning it on.
          </p>
        </Card>
      </>
    );
  }

  return (
    <>
      <PageHeader
        title="Pitch Video Studio"
        description="Paste or upload a Deck Spec — narration is generated with the platform's self-hosted voice engine, then rendered into a branded MP4."
      />

      <Card>
        <CardTitle>New pitch video</CardTitle>
        <div className="mb-3 rounded-lg border border-blue-200 bg-blue-50 px-3 py-2 text-xs text-blue-800">
          A pitch video is defined by a <strong>Deck Spec</strong> — a JSON document listing your
          scenes and their voiceover. Start from the template below (it contains one example of
          every scene layout), edit the text and narration, delete the scenes you don&apos;t need,
          and submit. The video is themed entirely from the brand&apos;s design tokens; each scene
          lasts exactly as long as its narration audio.
        </div>

        <details className="mb-3 rounded-lg border border-slate-200">
          <summary className="cursor-pointer select-none px-3 py-2 text-sm font-medium text-slate-600 hover:bg-slate-50">
            📖 Deck Spec format reference
          </summary>
          <div className="border-t border-slate-100 px-3 py-2">
            <table className="w-full text-xs">
              <tbody>
                {FORMAT_ROWS.map((r) => (
                  <tr key={r.field} className="border-b border-slate-100 last:border-0 align-top">
                    <td className="whitespace-nowrap py-1.5 pr-3 font-mono text-slate-700">{r.field}</td>
                    <td className="py-1.5 text-slate-500">{r.desc}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </details>

        <form onSubmit={submit} className="space-y-2">
          <div className="flex flex-wrap items-center gap-2">
            <Button type="button" variant="secondary" onClick={loadStarterTemplate}>
              Load starter template{selectedBrand ? ` for ${selectedBrand.name}` : ""}
            </Button>
            <Button type="button" variant="secondary" onClick={() => fileInputRef.current?.click()}>
              Upload Deck Spec (.json)
            </Button>
            <input
              ref={fileInputRef} type="file" accept="application/json" className="hidden"
              onChange={handleFileUpload}
            />
          </div>
          <textarea
            required rows={16} value={deckText} onChange={(e) => setDeckText(e.target.value)}
            placeholder='Paste your Deck Spec JSON here — or click "Load starter template" above to see the full format with one example of every scene layout.'
            className={ta}
          />
          {error ? <p className="text-xs text-red-600">{error}</p> : null}
          <Button type="submit" disabled={busy || !deckText.trim()}>
            {busy ? "Starting…" : "Generate video"}
          </Button>
        </form>
      </Card>

      {jobs.length ? (
        <Card className="mt-4">
          <CardTitle>Jobs</CardTitle>
          <ul className="space-y-3">
            {jobs.map((j) => (
              <li key={j.id} className="rounded-lg border border-slate-200 p-3 text-sm">
                <div className="flex items-center justify-between">
                  <span className="font-medium text-slate-700">{j.title}</span>
                  <span
                    className={
                      j.status === "succeeded" ? "text-green-600"
                        : j.status === "failed" ? "text-red-600"
                        : "text-amber-600"
                    }
                  >
                    {STATUS_LABEL[j.status] ?? j.status}
                  </span>
                </div>
                {j.progress_note ? <p className="mt-1 text-xs text-slate-400">{j.progress_note}</p> : null}
                {j.status === "failed" && j.error ? (
                  <p className="mt-1 text-xs text-red-600">{j.error}</p>
                ) : null}
                {j.status === "succeeded" && j.has_output ? (
                  <div className="mt-2 space-y-2">
                    <video src={pitchVideoApi.videoUrl(j.id)} controls className="max-h-80 w-full rounded" />
                    <a
                      href={pitchVideoApi.videoUrl(j.id)}
                      className="inline-block text-xs font-medium text-brand hover:underline"
                    >
                      Download MP4
                    </a>
                  </div>
                ) : null}
              </li>
            ))}
          </ul>
        </Card>
      ) : null}
    </>
  );
}
