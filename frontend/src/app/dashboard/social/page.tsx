"use client";

import { useCallback, useEffect, useState } from "react";

import { PageHeader } from "@/components/PageHeader";
import { Button } from "@/components/ui/Button";
import { Card, CardTitle } from "@/components/ui/Card";
import { Spinner } from "@/components/ui/Spinner";
import { ApiError, socialApi as connectionsApi, type SocialConnection } from "@/lib/api";
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
  const [connections, setConnections] = useState<SocialConnection[]>([]);
  const [chosenConn, setChosenConn] = useState<Record<string, string>>({});
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [platform, setPlatform] = useState("instagram");
  const [caption, setCaption] = useState("");
  const [scheduledAt, setScheduledAt] = useState("");

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const [status, p, conns] = await Promise.all([
        socialApi.status(),
        socialApi.posts(selectedBrandId),
        connectionsApi.list().catch(() => [] as SocialConnection[]),
      ]);
      setAdapters(status.adapters);
      setPosts(p);
      setConnections(conns);
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Failed to load social");
    } finally {
      setLoading(false);
    }
  }, [selectedBrandId]);

  // Active connections for a platform, used to pick which account to post to.
  const activeFor = useCallback(
    (p: string) => connections.filter((c) => c.platform === p && c.status === "active"),
    [connections],
  );

  useEffect(() => {
    void load();
  }, [load]);

  async function create(e: React.FormEvent) {
    e.preventDefault();
    if (!selectedBrandId) return;
    try {
      await socialApi.createPost({
        brand_id: selectedBrandId,
        platform,
        caption,
        // datetime-local has no timezone; interpreted in the browser's local
        // zone and converted to an ISO instant for the API.
        scheduled_at: scheduledAt ? new Date(scheduledAt).toISOString() : null,
      });
      setCaption("");
      setScheduledAt("");
      await load();
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Create failed");
    }
  }

  async function submitForApproval(id: string, connectionId?: string) {
    setNotice(null);
    setError(null);
    try {
      const r = await socialApi.submitForApproval(id, connectionId);
      setNotice(r.message);
      await load();
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Submit failed");
    }
  }

  // Right-hand action for a post row: account picker + submit, or a status chip.
  function renderActions(p: SocialPost) {
    if (p.state === "needs_review") {
      return (
        <span className="rounded-full bg-amber-100 px-2 py-0.5 text-xs font-medium text-amber-700">
          Pending approval
        </span>
      );
    }
    if (p.state === "published") {
      return (
        <span className="rounded-full bg-green-100 px-2 py-0.5 text-xs font-medium text-green-700">
          Published
        </span>
      );
    }
    if (p.state === "scheduled") {
      return (
        <span className="rounded-full bg-blue-100 px-2 py-0.5 text-xs font-medium text-blue-700">
          Scheduled for {p.scheduled_at ? new Date(p.scheduled_at).toLocaleString() : "—"}
        </span>
      );
    }
    if (p.state !== "draft" || !canEdit) return null;

    const conns = activeFor(p.platform);
    if (conns.length === 0) {
      return (
        <span className="text-xs text-slate-400">
          Connect {p.platform} in Settings → Social Connections
        </span>
      );
    }
    const chosen = chosenConn[p.id] ?? conns[0].id;
    return (
      <div className="flex items-center gap-2">
        {conns.length > 1 ? (
          <select
            value={chosen}
            onChange={(e) => setChosenConn((m) => ({ ...m, [p.id]: e.target.value }))}
            className="max-w-[11rem] rounded-lg border border-slate-300 px-2 py-1.5 text-xs"
            title="Choose which connected account to post to"
          >
            {conns.map((c) => (
              <option key={c.id} value={c.id}>
                {c.display_name ?? c.handle ?? c.external_id}
              </option>
            ))}
          </select>
        ) : null}
        <Button variant="secondary" onClick={() => void submitForApproval(p.id, chosen)}>
          Send for approval
        </Button>
      </div>
    );
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
        <CardTitle>Platform availability</CardTitle>
        <p className="mb-2 text-xs text-slate-400">
          Platforms whose OAuth is configured on the server. Connect your accounts
          under Settings → Social Connections, then submit posts for approval.
        </p>
        <div className="flex flex-wrap gap-2">
          {PLATFORMS.map((p) => (
            <span
              key={p}
              className={`rounded-full px-3 py-1 text-xs font-medium ${
                adapters[p] ? "bg-green-100 text-green-700" : "bg-slate-100 text-slate-500"
              }`}
            >
              {p}: {adapters[p] ? "available" : "not configured"}
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
            <div className="flex items-center gap-2">
              <label className="text-xs text-slate-500">Schedule for (optional):</label>
              <input
                type="datetime-local"
                value={scheduledAt}
                onChange={(e) => setScheduledAt(e.target.value)}
                min={new Date().toISOString().slice(0, 16)}
                className="rounded-lg border border-slate-300 px-3 py-2 text-sm"
              />
              {scheduledAt ? (
                <button
                  type="button"
                  onClick={() => setScheduledAt("")}
                  className="text-xs text-slate-400 hover:text-slate-600"
                >
                  Clear
                </button>
              ) : null}
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
                    {p.state === "draft" && p.scheduled_at ? (
                      <p className="mt-0.5 text-xs text-blue-500">
                        Will publish {new Date(p.scheduled_at).toLocaleString()} once approved
                      </p>
                    ) : null}
                  </div>
                  {renderActions(p)}
                </div>
              </Card>
            ))
          )}
        </div>
      )}
    </>
  );
}
