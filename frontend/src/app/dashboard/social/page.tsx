"use client";

import { useCallback, useEffect, useState } from "react";

import { PageHeader } from "@/components/PageHeader";
import { Button } from "@/components/ui/Button";
import { Card, CardTitle } from "@/components/ui/Card";
import { Spinner } from "@/components/ui/Spinner";
import { ApiError } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { useBrand } from "@/lib/brand";
import { socialApi } from "@/lib/resources";
import type { SocialPost } from "@/lib/types";

const PLATFORMS = ["linkedin", "instagram", "facebook", "twitter", "youtube", "tiktok"];

export default function SocialPage() {
  const { user } = useAuth();
  const { selectedBrandId } = useBrand();
  const canEdit = user ? user.role !== "viewer" : false;

  const [adapters, setAdapters] = useState<Record<string, boolean>>({});
  const [posts, setPosts] = useState<SocialPost[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [platform, setPlatform] = useState("instagram");
  const [caption, setCaption] = useState("");

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const [status, p] = await Promise.all([socialApi.status(), socialApi.posts(selectedBrandId)]);
      setAdapters(status.adapters);
      setPosts(p);
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Failed to load social");
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
      await socialApi.createPost({ brand_id: selectedBrandId, platform, caption });
      setCaption("");
      await load();
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Create failed");
    }
  }

  async function submitForApproval(id: string) {
    setNotice(null);
    setError(null);
    try {
      const r = await socialApi.submitForApproval(id);
      setNotice(r.message);
      await load();
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Submit failed");
    }
  }

  return (
    <>
      <PageHeader
        title="Social"
        description="Plan and draft posts across platforms. No scraping; live posting only via official APIs."
      />

      {error ? (
        <div className="mb-4 rounded-lg bg-red-50 px-3 py-2 text-sm text-red-700">{error}</div>
      ) : null}
      {notice ? (
        <div className="mb-4 rounded-lg bg-blue-50 px-3 py-2 text-sm text-blue-700">{notice}</div>
      ) : null}

      <Card className="mb-6">
        <CardTitle>Platform connections</CardTitle>
        <div className="flex flex-wrap gap-2">
          {PLATFORMS.map((p) => (
            <span
              key={p}
              className={`rounded-full px-3 py-1 text-xs font-medium ${
                adapters[p] ? "bg-green-100 text-green-700" : "bg-slate-100 text-slate-500"
              }`}
            >
              {p}: {adapters[p] ? "live" : "draft / copy-paste"}
            </span>
          ))}
        </div>
      </Card>

      {canEdit && selectedBrandId ? (
        <Card className="mb-6">
          <CardTitle>New post</CardTitle>
          <form onSubmit={create} className="space-y-2">
            <div className="flex gap-2">
              <select
                value={platform}
                onChange={(e) => setPlatform(e.target.value)}
                className="rounded-lg border border-slate-300 px-3 py-2 text-sm"
              >
                {PLATFORMS.map((p) => (
                  <option key={p} value={p}>
                    {p}
                  </option>
                ))}
              </select>
              <input
                required
                value={caption}
                onChange={(e) => setCaption(e.target.value)}
                placeholder="Caption…"
                className="grow rounded-lg border border-slate-300 px-3 py-2 text-sm"
              />
            </div>
            <Button type="submit">Add draft post</Button>
          </form>
        </Card>
      ) : null}

      {loading ? (
        <Spinner />
      ) : (
        <div className="space-y-3">
          {posts.length === 0 ? (
            <Card>
              <p className="text-sm text-slate-400">No posts yet.</p>
            </Card>
          ) : (
            posts.map((p) => (
              <Card key={p.id}>
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <div>
                    <span className="rounded-full bg-slate-100 px-2 py-0.5 text-xs font-medium text-slate-600">
                      {p.platform}
                    </span>
                    <span className="ml-2 text-xs capitalize text-slate-400">{p.state}</span>
                    <p className="mt-1 text-sm text-slate-700">{p.caption}</p>
                  </div>
                  {p.state === "draft" && canEdit ? (
                    <Button variant="secondary" onClick={() => void submitForApproval(p.id)}>
                      Send for approval
                    </Button>
                  ) : p.state === "needs_review" ? (
                    <span className="rounded-full bg-amber-100 px-2 py-0.5 text-xs font-medium text-amber-700">
                      Pending approval
                    </span>
                  ) : p.state === "published" ? (
                    <span className="rounded-full bg-green-100 px-2 py-0.5 text-xs font-medium text-green-700">
                      Published
                    </span>
                  ) : null}
                </div>
              </Card>
            ))
          )}
        </div>
      )}
    </>
  );
}
