"use client";

// Listing Video Studio — real-estate agents turn ~10 photos + listing details
// into a ~30s vertical (9:16) social video with an AI voiceover and a licensed
// music bed. Flow: fill the form → draft the script (deterministic, Fair
// Housing-screened) → review/edit → upload photos in order → render.

import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import { PageHeader } from "@/components/PageHeader";
import { Button } from "@/components/ui/Button";
import { Card, CardTitle } from "@/components/ui/Card";
import { Spinner } from "@/components/ui/Spinner";
import {
  ApiError,
  listingVideoApi,
  type ListingDetails,
  type ListingVideoJob,
} from "@/lib/api";
import { useBrand } from "@/lib/brand";

const input = "w-full rounded-lg border border-slate-300 px-3 py-2 text-sm focus:border-brand focus:outline-none focus:ring-1 focus:ring-brand";
const label = "mb-1 block text-xs font-medium text-slate-600";

const ACTIVE_STATUSES = new Set(["queued", "generating_audio", "rendering"]);

const STATUS_BADGES: Record<string, { label: string; cls: string }> = {
  queued:           { label: "Queued",     cls: "bg-slate-100 text-slate-700" },
  generating_audio: { label: "Voiceover…", cls: "bg-blue-100 text-blue-800" },
  rendering:        { label: "Rendering…", cls: "bg-blue-100 text-blue-800" },
  succeeded:        { label: "Ready",      cls: "bg-green-100 text-green-800" },
  failed:           { label: "Failed",     cls: "bg-red-100 text-red-800" },
  cancelled:        { label: "Cancelled",  cls: "bg-slate-100 text-slate-600" },
};

interface PhotoItem {
  file: File;
  url: string; // object URL for the thumbnail
}

export default function ListingVideosPage() {
  const { brands, selectedBrandId } = useBrand();
  const selectedBrand = brands.find((b) => b.id === selectedBrandId) ?? brands[0] ?? null;

  const [enabled, setEnabled] = useState<boolean | null>(null);
  const [minPhotos, setMinPhotos] = useState(3);
  const [maxPhotos, setMaxPhotos] = useState(15);
  const [musicTracks, setMusicTracks] = useState<string[]>([]);
  const [voices, setVoices] = useState<{ stock: string[]; personas: { id: string; name: string }[] }>({
    stock: [], personas: [],
  });
  // "" = server default · "stock:<name>" · "persona:<id>"
  const [voiceChoice, setVoiceChoice] = useState("");

  // Form
  const [details, setDetails] = useState<ListingDetails>({
    street: "", city: "", state: "", zip_code: "",
    beds: null, baths: null, sqft: null, lot: "", year_built: null,
    price_text: "", listing_type: "For Sale",
    features: [], hook: "", agent_name: "", agent_phone: "", brokerage: "",
  });
  const [featureText, setFeatureText] = useState("");
  const [photos, setPhotos] = useState<PhotoItem[]>([]);
  const [musicTrack, setMusicTrack] = useState("");
  // Landscape default: MLS photos are shot landscape and crop badly in 9:16.
  const [aspectRatio, setAspectRatio] = useState<"16:9" | "9:16">("16:9");

  // Script step
  const [script, setScript] = useState("");
  const [fhWarnings, setFhWarnings] = useState<string[]>([]);
  const [spokenSeconds, setSpokenSeconds] = useState<number | null>(null);
  const [drafting, setDrafting] = useState(false);

  // Jobs
  const [jobs, setJobs] = useState<ListingVideoJob[]>([]);
  // Per-failed-job voice override for Retry ("" = keep the job's voice).
  const [retryVoice, setRetryVoice] = useState<Record<string, string>>({});
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const fileInputRef = useRef<HTMLInputElement | null>(null);

  useEffect(() => {
    listingVideoApi.status()
      .then((s) => {
        setEnabled(s.enabled);
        setMinPhotos(s.min_photos);
        setMaxPhotos(s.max_photos);
        if (s.enabled) {
          listingVideoApi.musicTracks().then((m) => setMusicTracks(m.tracks)).catch(() => {});
          // Stock voices need a (possibly cold) worker round-trip — retry once
          // if the first answer came back without them.
          listingVideoApi.voices().then((v) => {
            setVoices(v);
            if (v.stock.length === 0) {
              setTimeout(() => {
                listingVideoApi.voices().then(setVoices).catch(() => {});
              }, 8000);
            }
          }).catch(() => {});
          void refreshJobs();
        }
      })
      .catch(() => setEnabled(false));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const refreshJobs = useCallback(async () => {
    try {
      setJobs(await listingVideoApi.listJobs());
    } catch {
      /* transient */
    }
  }, []);

  // Poll while any job is active.
  const hasActive = useMemo(() => jobs.some((j) => ACTIVE_STATUSES.has(j.status)), [jobs]);
  useEffect(() => {
    if (!hasActive) return;
    const t = setInterval(refreshJobs, 5000);
    return () => clearInterval(t);
  }, [hasActive, refreshJobs]);

  function setD<K extends keyof ListingDetails>(key: K, value: ListingDetails[K]) {
    setDetails((d) => ({ ...d, [key]: value }));
  }

  function addFeature() {
    const f = featureText.trim();
    if (!f) return;
    setD("features", [...details.features, f].slice(0, 10));
    setFeatureText("");
  }

  function onPickPhotos(files: FileList | null) {
    if (!files) return;
    const items = Array.from(files).map((file) => ({ file, url: URL.createObjectURL(file) }));
    setPhotos((prev) => [...prev, ...items].slice(0, maxPhotos));
    if (fileInputRef.current) fileInputRef.current.value = "";
  }

  function movePhoto(i: number, dir: -1 | 1) {
    setPhotos((prev) => {
      const next = [...prev];
      const j = i + dir;
      if (j < 0 || j >= next.length) return prev;
      [next[i], next[j]] = [next[j], next[i]];
      return next;
    });
  }

  function removePhoto(i: number) {
    setPhotos((prev) => {
      URL.revokeObjectURL(prev[i].url);
      return prev.filter((_, k) => k !== i);
    });
  }

  async function onDraftScript() {
    setError(null);
    setDrafting(true);
    try {
      const res = await listingVideoApi.draftScript(details);
      setScript(res.script);
      setFhWarnings(res.fair_housing_flags);
      setSpokenSeconds(res.estimated_spoken_seconds);
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Could not draft the script.");
    } finally {
      setDrafting(false);
    }
  }

  async function onSubmit() {
    if (!selectedBrand) {
      setError("Create a brand first — the video uses your brand's colors and fonts.");
      return;
    }
    setError(null);
    setSubmitting(true);
    try {
      const [kind, value] = voiceChoice ? voiceChoice.split(":", 2) : ["", ""];
      await listingVideoApi.createJob({
        brandSlug: selectedBrand.slug,
        details,
        script,
        musicTrack,
        photos: photos.map((p) => p.file),
        aspectRatio,
        voiceMode: kind === "persona" ? "clone" : "stock",
        speakerName: kind === "stock" ? value : "",
        personaIdentityId: kind === "persona" ? value : "",
      });
      await refreshJobs();
      setScript("");
      setFhWarnings([]);
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Could not create the video job.");
    } finally {
      setSubmitting(false);
    }
  }

  if (enabled === null) {
    return (
      <div className="flex h-64 items-center justify-center">
        <Spinner />
      </div>
    );
  }

  if (!enabled) {
    return (
      <div>
        <PageHeader title="Listing Videos" description="Turn listing photos into 30-second social videos" />
        <Card>
          <p className="text-sm text-slate-600">
            Listing Video Studio isn&apos;t enabled on this server yet. Ask your administrator to set{" "}
            <code className="rounded bg-slate-100 px-1">LISTING_VIDEO_ENABLED=true</code> (requires the
            voice + render workers).
          </p>
        </Card>
      </div>
    );
  }

  const canDraft = details.street.trim() && details.city.trim() && details.state.trim();
  const canSubmit =
    Boolean(canDraft) && script.trim().length > 0 &&
    photos.length >= minPhotos && photos.length <= maxPhotos && !submitting;

  return (
    <div className="space-y-6">
      <PageHeader
        title="Listing Videos"
        description="10 photos in, a 30-second TikTok/Instagram-ready video out — voiceover and music included"
      />

      {error && <p className="rounded-lg bg-red-50 px-3 py-2 text-sm text-red-700">{error}</p>}

      <div className="grid gap-6 lg:grid-cols-2">
        {/* -------------------------------------------------- Listing form */}
        <Card>
          <CardTitle>1 · Listing details</CardTitle>
          <div className="mt-3 grid grid-cols-2 gap-3">
            <div className="col-span-2">
              <label className={label}>Street address *</label>
              <input className={input} value={details.street} onChange={(e) => setD("street", e.target.value)} placeholder="412 Sheridan Rd" />
            </div>
            <div>
              <label className={label}>City *</label>
              <input className={input} value={details.city} onChange={(e) => setD("city", e.target.value)} placeholder="Winthrop Harbor" />
            </div>
            <div className="grid grid-cols-2 gap-3">
              <div>
                <label className={label}>State *</label>
                <input className={input} value={details.state} onChange={(e) => setD("state", e.target.value)} placeholder="IL" />
              </div>
              <div>
                <label className={label}>ZIP</label>
                <input className={input} value={details.zip_code} onChange={(e) => setD("zip_code", e.target.value)} />
              </div>
            </div>
            <div className="grid grid-cols-3 gap-3 col-span-2">
              <div>
                <label className={label}>Beds</label>
                <input className={input} type="number" min={0} value={details.beds ?? ""} onChange={(e) => setD("beds", e.target.value ? Number(e.target.value) : null)} />
              </div>
              <div>
                <label className={label}>Baths</label>
                <input className={input} type="number" min={0} step={0.5} value={details.baths ?? ""} onChange={(e) => setD("baths", e.target.value ? Number(e.target.value) : null)} />
              </div>
              <div>
                <label className={label}>Sq ft</label>
                <input className={input} type="number" min={0} value={details.sqft ?? ""} onChange={(e) => setD("sqft", e.target.value ? Number(e.target.value) : null)} />
              </div>
            </div>
            <div>
              <label className={label}>Price (display text)</label>
              <input className={input} value={details.price_text} onChange={(e) => setD("price_text", e.target.value)} placeholder="$489,000" />
            </div>
            <div>
              <label className={label}>Listing type</label>
              <select className={input} value={details.listing_type} onChange={(e) => setD("listing_type", e.target.value)}>
                {["For Sale", "Just Listed", "Open House", "For Rent", "Price Improvement", "Sold"].map((t) => (
                  <option key={t}>{t}</option>
                ))}
              </select>
            </div>
            <div>
              <label className={label}>Lot</label>
              <input className={input} value={details.lot} onChange={(e) => setD("lot", e.target.value)} placeholder="0.4 acre lot" />
            </div>
            <div>
              <label className={label}>Year built</label>
              <input className={input} type="number" value={details.year_built ?? ""} onChange={(e) => setD("year_built", e.target.value ? Number(e.target.value) : null)} />
            </div>

            <div className="col-span-2">
              <label className={label}>Features (up to 10 — shown as on-screen chips)</label>
              <div className="flex gap-2">
                <input
                  className={input} value={featureText}
                  onChange={(e) => setFeatureText(e.target.value)}
                  onKeyDown={(e) => { if (e.key === "Enter") { e.preventDefault(); addFeature(); } }}
                  placeholder="Chef's kitchen"
                />
                <Button type="button" variant="secondary" onClick={addFeature}>Add</Button>
              </div>
              {details.features.length > 0 && (
                <div className="mt-2 flex flex-wrap gap-1.5">
                  {details.features.map((f, i) => (
                    <span key={`${f}-${i}`} className="inline-flex items-center gap-1 rounded-full bg-brand/10 px-2.5 py-0.5 text-xs font-medium text-brand">
                      {f}
                      <button
                        type="button" className="text-brand/60 hover:text-brand"
                        onClick={() => setD("features", details.features.filter((_, k) => k !== i))}
                      >
                        ×
                      </button>
                    </span>
                  ))}
                </div>
              )}
            </div>

            <div className="col-span-2">
              <label className={label}>Opening hook (optional, one sentence)</label>
              <input className={input} value={details.hook} onChange={(e) => setD("hook", e.target.value)} placeholder="Lake Michigan sunrises from your own back deck" />
            </div>

            <div>
              <label className={label}>Agent name</label>
              <input className={input} value={details.agent_name} onChange={(e) => setD("agent_name", e.target.value)} />
            </div>
            <div>
              <label className={label}>Agent phone</label>
              <input className={input} value={details.agent_phone} onChange={(e) => setD("agent_phone", e.target.value)} />
            </div>
            <div className="col-span-2">
              <label className={label}>Brokerage</label>
              <input className={input} value={details.brokerage} onChange={(e) => setD("brokerage", e.target.value)} />
            </div>
          </div>

          <div className="mt-4">
            <Button onClick={onDraftScript} disabled={!canDraft || drafting}>
              {drafting ? "Drafting…" : script ? "Re-draft script" : "Draft voiceover script →"}
            </Button>
          </div>
        </Card>

        <div className="space-y-6">
          {/* -------------------------------------------------- Script review */}
          <Card>
            <CardTitle>2 · Voiceover script</CardTitle>
            {script ? (
              <>
                <p className="mt-1 text-xs text-slate-500">
                  Edit freely — this exact text is spoken.
                  {spokenSeconds ? ` ~${spokenSeconds}s spoken.` : ""}
                </p>
                <textarea
                  className={`${input} mt-2 font-normal`} rows={7}
                  value={script} onChange={(e) => setScript(e.target.value)}
                />
                {fhWarnings.length > 0 && (
                  <p className="mt-2 rounded-lg bg-amber-50 px-3 py-2 text-xs text-amber-800">
                    <strong>Fair Housing check:</strong> remove {fhWarnings.map((f) => `“${f}”`).join(", ")} —
                    describe the property, not the buyer. Submissions containing these are rejected.
                  </p>
                )}
              </>
            ) : (
              <p className="mt-2 text-sm text-slate-500">
                Fill in the listing details and draft the script. You&apos;ll review and edit it before
                anything is rendered.
              </p>
            )}
          </Card>

          {/* -------------------------------------------------- Photos */}
          <Card>
            <CardTitle>3 · Photos ({photos.length}/{maxPhotos})</CardTitle>
            <p className="mt-1 text-xs text-slate-500">
              {minPhotos}–{maxPhotos} photos, in the order they should appear. Lead with the best exterior shot.
            </p>
            <input
              ref={fileInputRef} type="file" multiple accept="image/jpeg,image/png,image/webp"
              className="mt-2 block w-full text-sm text-slate-500 file:mr-3 file:rounded-lg file:border-0 file:bg-brand/10 file:px-3 file:py-1.5 file:text-sm file:font-medium file:text-brand hover:file:bg-brand/20"
              onChange={(e) => onPickPhotos(e.target.files)}
            />
            {photos.length > 0 && (
              <div className="mt-3 grid grid-cols-3 gap-2 sm:grid-cols-5">
                {photos.map((p, i) => (
                  <div key={p.url} className="group relative overflow-hidden rounded-lg border border-slate-200">
                    {/* eslint-disable-next-line @next/next/no-img-element */}
                    <img src={p.url} alt={`Photo ${i + 1}`} className="aspect-square w-full object-cover" />
                    <span className="absolute left-1 top-1 rounded bg-black/60 px-1.5 text-xs font-bold text-white">{i + 1}</span>
                    <div className="absolute inset-x-0 bottom-0 flex justify-center gap-1 bg-black/50 py-0.5 opacity-0 transition-opacity group-hover:opacity-100">
                      <button type="button" className="px-1 text-xs text-white" onClick={() => movePhoto(i, -1)}>←</button>
                      <button type="button" className="px-1 text-xs text-white" onClick={() => removePhoto(i)}>✕</button>
                      <button type="button" className="px-1 text-xs text-white" onClick={() => movePhoto(i, 1)}>→</button>
                    </div>
                  </div>
                ))}
              </div>
            )}

            <div className="mt-4">
              <label className={label}>Orientation</label>
              <div className="flex gap-2">
                {([
                  ["16:9", "Landscape · YouTube, Facebook, websites"],
                  ["9:16", "Portrait · TikTok, Reels"],
                ] as const).map(([value, text]) => (
                  <button
                    key={value} type="button"
                    onClick={() => setAspectRatio(value)}
                    className={`flex-1 rounded-lg border px-3 py-2 text-left text-xs transition-colors ${
                      aspectRatio === value
                        ? "border-brand bg-brand/5 text-brand font-medium"
                        : "border-slate-200 text-slate-600 hover:border-slate-300"
                    }`}
                  >
                    {value === "16:9" ? "▭ " : "▯ "}{text}
                  </button>
                ))}
              </div>
            </div>

            <div className="mt-4 grid gap-3 sm:grid-cols-2">
              <div>
                <label className={label}>Voiceover voice</label>
                <select className={input} value={voiceChoice} onChange={(e) => setVoiceChoice(e.target.value)}>
                  <option value="">Default voice</option>
                  {voices.stock.length > 0 && (
                    <optgroup label="Stock voices">
                      {voices.stock.map((v) => <option key={v} value={`stock:${v}`}>{v}</option>)}
                    </optgroup>
                  )}
                  {voices.personas.length > 0 && (
                    <optgroup label="Your persona voices">
                      {voices.personas.map((p) => (
                        <option key={p.id} value={`persona:${p.id}`}>{p.name}</option>
                      ))}
                    </optgroup>
                  )}
                </select>
                {voices.personas.length === 0 && (
                  <p className="mt-1 text-xs text-slate-400">
                    Consented Avatar Personas with a voice sample appear here too.
                  </p>
                )}
              </div>
              <div>
                <label className={label}>Background music</label>
                <select
                  className={input} value={musicTrack} disabled={musicTracks.length === 0}
                  onChange={(e) => setMusicTrack(e.target.value)}
                >
                  <option value="">No music</option>
                  {musicTracks.map((t) => <option key={t} value={t}>{t.replace(/\.[a-z0-9]+$/i, "")}</option>)}
                </select>
                {musicTracks.length === 0 && (
                  <p className="mt-1 text-xs text-slate-400">
                    No tracks installed on the server yet — see app/music/README.md.
                  </p>
                )}
              </div>
            </div>

            <div className="mt-4">
              <Button onClick={onSubmit} disabled={!canSubmit}>
                {submitting ? "Uploading…" : "Create video 🎬"}
              </Button>
              {!canSubmit && photos.length > 0 && photos.length < minPhotos && (
                <p className="mt-1 text-xs text-slate-500">Add at least {minPhotos} photos.</p>
              )}
            </div>
          </Card>
        </div>
      </div>

      {/* -------------------------------------------------- Jobs */}
      <Card>
        <CardTitle>Your videos</CardTitle>
        {jobs.length === 0 ? (
          <p className="mt-2 text-sm text-slate-500">No videos yet — your renders will appear here.</p>
        ) : (
          <div className="mt-3 divide-y divide-slate-100">
            {jobs.map((j) => {
              const badge = STATUS_BADGES[j.status] ?? STATUS_BADGES.queued;
              return (
                <div key={j.id} className="flex items-center justify-between gap-3 py-3">
                  <div className="min-w-0">
                    <p className="truncate text-sm font-medium text-slate-800">{j.address}</p>
                    <p className="text-xs text-slate-500">
                      {/* API timestamps are UTC but unmarked — tag them so
                          they render in the viewer's local time. */}
                      {j.photo_count} photos · {new Date(/[Z+]/.test(j.created_at.slice(-6)) ? j.created_at : j.created_at + "Z").toLocaleString()}
                      {j.progress_note ? ` · ${j.progress_note}` : ""}
                    </p>
                    {j.status === "failed" && j.error && (
                      <p className="mt-0.5 text-xs text-red-600">
                        {/* The LAST line of a traceback is the actual error. */}
                        {(j.error.trim().split("\n").filter(Boolean).pop() ?? j.error).slice(0, 200)}
                      </p>
                    )}
                  </div>
                  <div className="flex shrink-0 items-center gap-2">
                    <span className={`rounded-full px-2.5 py-0.5 text-xs font-medium ${badge.cls}`}>
                      {badge.label}
                    </span>
                    {j.status === "succeeded" && j.has_output && (
                      <a
                        href={listingVideoApi.videoUrl(j.id)}
                        className="rounded-lg bg-brand px-3 py-1.5 text-xs font-medium text-white hover:bg-brand/90"
                      >
                        Download MP4
                      </a>
                    )}
    {j.status === "failed" && (
                      <>
                        <select
                          className="rounded-lg border border-slate-300 px-2 py-1.5 text-xs text-slate-600"
                          value={retryVoice[j.id] ?? ""}
                          onChange={(e) => setRetryVoice((m) => ({ ...m, [j.id]: e.target.value }))}
                        >
                          <option value="">Same voice ({j.voice_mode === "clone" ? "persona" : j.speaker_name || "default"})</option>
                          {voices.stock.map((v) => <option key={v} value={`stock:${v}`}>{v}</option>)}
                          {voices.personas.map((p) => (
                            <option key={p.id} value={`persona:${p.id}`}>{p.name} (persona)</option>
                          ))}
                        </select>
                        <button
                          type="button"
                          onClick={() => {
                            const choice = retryVoice[j.id] ?? "";
                            const [kind, value] = choice ? choice.split(":", 2) : ["", ""];
                            const voice = kind === "stock"
                              ? { voiceMode: "stock" as const, speakerName: value }
                              : kind === "persona"
                                ? { voiceMode: "clone" as const, personaIdentityId: value }
                                : undefined;
                            void listingVideoApi.retryJob(j.id, voice).then(refreshJobs).catch((e) =>
                              setError(e instanceof ApiError ? e.message : "Could not retry the job."),
                            );
                          }}
                          className="rounded-lg border border-brand px-3 py-1.5 text-xs font-medium text-brand hover:bg-brand/5"
                        >
                          Retry
                        </button>
                      </>
                    )}
                  </div>
                </div>
              );
            })}
          </div>
        )}
      </Card>
    </div>
  );
}
