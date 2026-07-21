"use client";

import { useCallback, useEffect, useState } from "react";

import { PageHeader } from "@/components/PageHeader";
import { Button } from "@/components/ui/Button";
import { Card, CardTitle } from "@/components/ui/Card";
import { Spinner } from "@/components/ui/Spinner";
import { ApiError } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { useBrand } from "@/lib/brand";
import { platformLabel } from "@/lib/platforms";
import { aiApi, contentApi, socialApi } from "@/lib/resources";
import type { ContentItem } from "@/lib/types";

const CHANNELS = [
  "linkedin", "twitter", "instagram", "facebook", "youtube_short", "tiktok",
  "blog", "newsletter", "video_15", "video_30", "video_45", "video_60",
];

const STATE_STYLES: Record<string, string> = {
  draft: "bg-slate-100 text-slate-500",
  needs_review: "bg-amber-100 text-amber-700",
  approved: "bg-blue-100 text-blue-700",
  scheduled: "bg-indigo-100 text-indigo-700",
  published: "bg-green-100 text-green-700",
  archived: "bg-slate-100 text-slate-400",
};

const NEXT: Record<string, { action: string; label: string; admin?: boolean }[]> = {
  draft: [{ action: "submit", label: "Submit for review" }],
  needs_review: [{ action: "approve", label: "Approve" }],
  approved: [{ action: "publish", label: "Publish", admin: true }],
  scheduled: [{ action: "publish", label: "Publish", admin: true }],
};

export default function ContentPage() {
  const { user } = useAuth();
  const { selectedBrandId } = useBrand();
  const canEdit = user ? user.role !== "viewer" : false;
  const isAdmin = user?.role === "admin" || user?.role === "owner";

  const [items, setItems] = useState<ContentItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [channel, setChannel] = useState("linkedin");
  const [title, setTitle] = useState("");
  const [body, setBody] = useState("");
  const [topic, setTopic] = useState("");
  const [ideas, setIdeas] = useState<string[]>([]);
  const [media, setMedia] = useState<{ url: string; kind: string; filename: string; preview: string }[]>([]);
  const [uploading, setUploading] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const params: Record<string, string> = {};
      if (selectedBrandId) params.brand_id = selectedBrandId;
      setItems(await contentApi.list(params));
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Failed to load content");
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
    try {
      await contentApi.create({
        brand_id: selectedBrandId, channel, title, body,
        media_urls: media.map((m) => m.url),
      });
      setTitle("");
      setBody("");
      media.forEach((m) => URL.revokeObjectURL(m.preview));
      setMedia([]);
      await load();
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Create failed");
    }
  }

  async function transition(id: string, action: string) {
    try {
      await contentApi.transition(id, action);
      await load();
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Action failed");
    }
  }

  async function onAttach(files: FileList | null) {
    if (!files || !selectedBrandId) return;
    setError(null);
    setUploading(true);
    try {
      for (const file of Array.from(files)) {
        const res = await socialApi.uploadMedia(file, selectedBrandId);
        setMedia((m) => [...m, { url: res.media_url, kind: res.kind, filename: res.filename, preview: URL.createObjectURL(file) }]);
      }
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Upload failed");
    } finally {
      setUploading(false);
    }
  }

  function removeMedia(i: number) {
    setMedia((m) => {
      URL.revokeObjectURL(m[i].preview);
      return m.filter((_, k) => k !== i);
    });
  }

  async function draftWithAI() {
    if (!selectedBrandId || !title) return;
    try {
      const r = await aiApi.draftSocial(selectedBrandId, channel, title);
      setBody(r.text);
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "AI draft failed");
    }
  }

  async function genIdeas() {
    if (!selectedBrandId) return;
    try {
      const r = await contentApi.ideas({ brand_id: selectedBrandId, channel, count: 5, topic });
      setIdeas(r.ideas);
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Idea generation failed");
    }
  }

  return (
    <>
      <PageHeader
        title="Content"
        description="Draft → review → approve → schedule → publish. Nothing posts without approval."
      />
      {error ? (
        <div className="mb-4 rounded-lg bg-red-50 px-3 py-2 text-sm text-red-700">{error}</div>
      ) : null}

      {canEdit && !selectedBrandId ? (
        <Card className="mb-6 border-dashed">
          <p className="text-sm text-slate-500">
            Select a specific brand in the <span className="font-medium">Brand</span> menu above to
            create content. Content items belong to one brand, so the composer is hidden while
            “All Brands” is selected.
          </p>
        </Card>
      ) : null}

      {canEdit && selectedBrandId ? (
        <div className="mb-6 grid grid-cols-1 gap-4 lg:grid-cols-2">
          <Card>
            <CardTitle>New content</CardTitle>
            <form onSubmit={create} className="space-y-2">
              <div className="flex gap-2">
                <select
                  value={channel}
                  onChange={(e) => setChannel(e.target.value)}
                  className="rounded-lg border border-slate-300 px-3 py-2 text-sm"
                >
                  {CHANNELS.map((c) => (
                    <option key={c} value={c}>
                      {platformLabel(c)}
                    </option>
                  ))}
                </select>
                <input
                  required
                  value={title}
                  onChange={(e) => setTitle(e.target.value)}
                  placeholder="Title"
                  className="grow rounded-lg border border-slate-300 px-3 py-2 text-sm"
                />
              </div>
              <textarea
                value={body}
                onChange={(e) => setBody(e.target.value)}
                rows={3}
                placeholder="Body / caption / script…"
                className="w-full rounded-lg border border-slate-300 px-3 py-2 text-sm"
              />
              <div>
                <div className="flex flex-wrap items-center gap-2">
                  {media.map((m, i) => (
                    <div key={m.preview} className="group relative h-14 w-14 overflow-hidden rounded-lg border border-slate-200">
                      {m.kind === "video" ? (
                        // eslint-disable-next-line jsx-a11y/media-has-caption
                        <video src={m.preview} className="h-full w-full object-cover" />
                      ) : (
                        // eslint-disable-next-line @next/next/no-img-element
                        <img src={m.preview} alt={m.filename} className="h-full w-full object-cover" />
                      )}
                      <button
                        type="button"
                        onClick={() => removeMedia(i)}
                        className="absolute right-0 top-0 bg-black/60 px-1 text-xs text-white opacity-0 transition-opacity group-hover:opacity-100"
                      >
                        ✕
                      </button>
                    </div>
                  ))}
                  <label className="flex h-14 w-14 cursor-pointer items-center justify-center rounded-lg border border-dashed border-slate-300 text-xl text-slate-400 hover:border-brand hover:text-brand">
                    {uploading ? "…" : "+"}
                    <input
                      type="file" multiple accept="image/*,video/*" className="hidden"
                      onChange={(e) => { void onAttach(e.target.files); e.target.value = ""; }}
                    />
                  </label>
                </div>
                <p className="mt-1 text-xs text-slate-400">Photos / videos (optional) — saved with this content draft.</p>
              </div>
              <div className="flex gap-2">
                <Button type="submit">Add draft</Button>
                <Button type="button" variant="secondary" onClick={() => void draftWithAI()}>
                  ✨ Draft with AI
                </Button>
              </div>
            </form>
          </Card>
          <Card>
            <CardTitle>Idea generator</CardTitle>
            <div className="flex gap-2">
              <input
                value={topic}
                onChange={(e) => setTopic(e.target.value)}
                placeholder="Topic (e.g. AI security)"
                className="grow rounded-lg border border-slate-300 px-3 py-2 text-sm"
              />
              <Button variant="secondary" onClick={() => void genIdeas()}>
                Generate
              </Button>
            </div>
            <ul className="mt-3 list-disc space-y-1 pl-5 text-sm text-slate-600">
              {ideas.map((idea, i) => (
                <li key={i}>{idea}</li>
              ))}
            </ul>
          </Card>
        </div>
      ) : null}

      {loading ? (
        <Spinner />
      ) : (
        <Card className="overflow-x-auto p-0">
          <table className="w-full text-sm">
            <thead className="border-b border-slate-200 text-left text-xs uppercase text-slate-400">
              <tr>
                <th className="px-4 py-3">Title</th>
                <th className="px-4 py-3">Channel</th>
                <th className="px-4 py-3">State</th>
                <th className="px-4 py-3" />
              </tr>
            </thead>
            <tbody>
              {items.length === 0 ? (
                <tr>
                  <td colSpan={4} className="px-4 py-6 text-center text-slate-400">
                    No content yet.
                  </td>
                </tr>
              ) : (
                items.map((c) => (
                  <tr key={c.id} className="border-b border-slate-100 last:border-0">
                    <td className="px-4 py-3 font-medium text-slate-800">{c.title}</td>
                    <td className="px-4 py-3 text-slate-500">{platformLabel(c.channel)}</td>
                    <td className="px-4 py-3">
                      <span
                        className={`rounded-full px-2 py-0.5 text-xs font-medium ${STATE_STYLES[c.state]}`}
                      >
                        {c.state.replace(/_/g, " ")}
                      </span>
                    </td>
                    <td className="px-4 py-3 text-right">
                      {canEdit
                        ? (NEXT[c.state] ?? [])
                            .filter((a) => !a.admin || isAdmin)
                            .map((a) => (
                              <Button
                                key={a.action}
                                variant="ghost"
                                onClick={() => void transition(c.id, a.action)}
                              >
                                {a.label}
                              </Button>
                            ))
                        : null}
                    </td>
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
