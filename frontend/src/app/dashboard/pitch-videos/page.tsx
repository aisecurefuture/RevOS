"use client";

import { useCallback, useEffect, useRef, useState } from "react";

import { PageHeader } from "@/components/PageHeader";
import { Button } from "@/components/ui/Button";
import { Card, CardTitle } from "@/components/ui/Card";
import { Spinner } from "@/components/ui/Spinner";
import { ApiError, pitchVideoApi, type PitchVideoJob } from "@/lib/api";
import { useBrand } from "@/lib/brand";

const ta = "w-full rounded-lg border border-slate-300 px-3 py-2 text-sm font-mono";

function starterDeck(brandSlug: string): string {
  return JSON.stringify(
    {
      brandId: brandSlug,
      title: "Untitled deck",
      aspectRatio: "16:9",
      voice: "",
      scenes: [
        {
          id: "hero",
          layout: "hero",
          variant: "dark",
          content: { eyebrow: "", headline: "Your headline here.", sub: "A supporting line." },
          narration: "Spoken voiceover text for this scene.",
        },
        {
          id: "close",
          layout: "close",
          variant: "dark",
          content: { headline: "Let's talk.", sub: "yourcompany.com" },
          narration: "Closing line, spoken.",
        },
      ],
    },
    null,
    2,
  );
}

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
          The Deck Spec carries its own <code>brandId</code> (a brand&apos;s slug) — the video is themed
          entirely from that brand&apos;s design tokens. Narration voice comes from the Deck Spec&apos;s{" "}
          <code>voice</code> field, or your account&apos;s default if omitted.
        </div>
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
            placeholder="Paste your Deck Spec JSON here…"
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
