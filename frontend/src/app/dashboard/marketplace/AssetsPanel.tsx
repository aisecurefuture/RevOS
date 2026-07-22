"use client";

import { useCallback, useEffect, useState } from "react";

import { Button } from "@/components/ui/Button";
import { Card, CardTitle } from "@/components/ui/Card";
import { Spinner } from "@/components/ui/Spinner";
import { ApiError } from "@/lib/api";
import { platformLabel } from "@/lib/platforms";
import { workspaceApi } from "@/lib/resources";
import type {
  AssetApproval,
  AssetComment,
  AssetKind,
  AssetVersion,
  Brand,
  Collaboration,
  CollaborationAsset,
} from "@/lib/types";

const PLATFORMS = ["instagram", "facebook", "linkedin", "threads", "twitter", "youtube", "tiktok"];

const STATE_STYLE: Record<string, string> = {
  draft: "bg-slate-100 text-slate-500",
  in_review: "bg-blue-100 text-blue-700",
  changes_requested: "bg-amber-100 text-amber-700",
  approved: "bg-green-100 text-green-700",
  published: "bg-purple-100 text-purple-700",
};

const INPUT =
  "w-full rounded-lg border border-slate-300 px-3 py-2 text-sm focus:border-brand focus:outline-none focus:ring-1 focus:ring-brand";
const LABEL = "mb-1 block text-xs font-medium text-slate-500";

export function AssetsPanel({
  collab, role, myBrands, setNotice,
}: {
  collab: Collaboration;
  role: "creator" | "brand";
  myBrands: Brand[];
  setNotice: (s: string | null) => void;
}) {
  const [assets, setAssets] = useState<CollaborationAsset[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [showNew, setShowNew] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      setAssets(await workspaceApi.listAssets(collab.id));
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Failed to load drafts");
    } finally {
      setLoading(false);
    }
  }, [collab.id]);

  useEffect(() => {
    void load();
  }, [load]);

  const selected = assets.find((a) => a.id === selectedId) ?? null;
  const canPropose = collab.state !== "ended";

  return (
    <Card>
      <div className="mb-2 flex items-center justify-between">
        <CardTitle>Shared drafts</CardTitle>
        {canPropose ? (
          <Button variant="secondary" onClick={() => setShowNew(true)}>New draft</Button>
        ) : null}
      </div>
      <p className="mb-3 text-xs text-slate-500">
        Draft the post together — either side proposes, both approve before it goes anywhere.
        Approving publishes straight into the normal content/social pipeline.
      </p>

      {error ? (
        <div className="mb-3 rounded-lg bg-red-50 px-3 py-2 text-sm text-red-700">{error}</div>
      ) : null}

      {loading ? (
        <Spinner />
      ) : assets.length === 0 ? (
        <p className="text-sm text-slate-400">No drafts yet.</p>
      ) : (
        <div className="mb-3 space-y-1.5">
          {assets.map((a) => (
            <button
              key={a.id}
              type="button"
              onClick={() => setSelectedId(a.id === selectedId ? null : a.id)}
              className={`flex w-full items-center justify-between gap-2 rounded-lg border px-3 py-2 text-left text-sm ${
                selectedId === a.id ? "border-brand bg-brand/5" : "border-slate-200 bg-white hover:bg-slate-50"
              }`}
            >
              <span className="text-slate-700">
                {a.title || `Untitled ${a.kind}`} <span className="text-xs text-slate-400">v{a.current_version}</span>
              </span>
              <span className={`rounded-full px-2 py-0.5 text-xs font-medium ${STATE_STYLE[a.state]}`}>
                {a.state.replace(/_/g, " ")}
              </span>
            </button>
          ))}
        </div>
      )}

      {selected ? (
        <AssetDetail
          key={selected.id}
          asset={selected}
          collab={collab}
          role={role}
          myBrands={myBrands}
          setNotice={setNotice}
          onChanged={load}
        />
      ) : null}

      {showNew ? (
        <NewAssetModal
          collab={collab}
          onClose={() => setShowNew(false)}
          onCreated={(id) => {
            setNotice("Draft created.");
            setShowNew(false);
            void load();
            setSelectedId(id);
          }}
        />
      ) : null}
    </Card>
  );
}

function NewAssetModal({
  collab, onClose, onCreated,
}: { collab: Collaboration; onClose: () => void; onCreated: (id: string) => void }) {
  const [kind, setKind] = useState<AssetKind>("text");
  const [title, setTitle] = useState("");
  const [caption, setCaption] = useState("");
  const [mediaUrl, setMediaUrl] = useState("");
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const canSave = (caption.trim().length > 0 || mediaUrl.trim().length > 0) && !saving;

  async function save() {
    if (!canSave) return;
    setSaving(true);
    setError(null);
    try {
      const created = await workspaceApi.createAsset(collab.id, {
        kind,
        title: title.trim() || undefined,
        caption: caption.trim() || undefined,
        media_urls: mediaUrl.trim() ? [mediaUrl.trim()] : [],
      });
      onCreated(created.id);
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Failed to create draft");
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className="fixed inset-0 z-50 flex items-start justify-center overflow-y-auto bg-black/40 p-4 sm:p-8" onClick={onClose}>
      <div className="w-full max-w-md rounded-xl bg-white p-6 shadow-xl" onClick={(e) => e.stopPropagation()}>
        <h2 className="mb-3 text-lg font-semibold text-slate-800">Propose a draft</h2>
        {error ? <div className="mb-3 rounded-lg bg-red-50 px-3 py-2 text-sm text-red-700">{error}</div> : null}
        <div className="space-y-3">
          <div>
            <label className={LABEL}>Type</label>
            <select value={kind} onChange={(e) => setKind(e.target.value as AssetKind)} className={INPUT}>
              <option value="text">Text</option>
              <option value="image">Image</option>
              <option value="video">Video</option>
            </select>
          </div>
          <div>
            <label className={LABEL}>Title (internal, optional)</label>
            <input value={title} onChange={(e) => setTitle(e.target.value)} className={INPUT} />
          </div>
          <div>
            <label className={LABEL}>Caption</label>
            <textarea value={caption} onChange={(e) => setCaption(e.target.value)} rows={4} className={INPUT} />
          </div>
          {kind !== "text" ? (
            <div>
              <label className={LABEL}>{kind === "image" ? "Image URL" : "Video URL"}</label>
              <input value={mediaUrl} onChange={(e) => setMediaUrl(e.target.value)} placeholder="https://…" className={INPUT} />
            </div>
          ) : null}
          <div className="flex justify-end gap-2 pt-1">
            <Button type="button" variant="secondary" onClick={onClose}>Cancel</Button>
            <Button type="button" onClick={() => void save()} disabled={!canSave}>
              {saving ? "Saving…" : "Propose draft"}
            </Button>
          </div>
        </div>
      </div>
    </div>
  );
}

function AssetDetail({
  asset, collab, role, myBrands, setNotice, onChanged,
}: {
  asset: CollaborationAsset;
  collab: Collaboration;
  role: "creator" | "brand";
  myBrands: Brand[];
  setNotice: (s: string | null) => void;
  onChanged: () => void;
}) {
  const [versions, setVersions] = useState<AssetVersion[]>([]);
  const [comments, setComments] = useState<AssetComment[]>([]);
  const [approvals, setApprovals] = useState<AssetApproval[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [commentBody, setCommentBody] = useState("");
  const [note, setNote] = useState("");
  const [showRevise, setShowRevise] = useState(false);
  const [reviseCaption, setReviseCaption] = useState("");
  const [reviseMedia, setReviseMedia] = useState("");
  const [showPublish, setShowPublish] = useState(false);

  const myAccountId = role === "creator" ? collab.creator_account_id : collab.brand_account_id;
  const theirRoleLabel = role === "creator" ? "brand" : "creator";

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const [v, c, a] = await Promise.all([
        workspaceApi.listVersions(collab.id, asset.id),
        workspaceApi.listAssetComments(collab.id, asset.id),
        workspaceApi.listAssetApprovals(collab.id, asset.id),
      ]);
      setVersions(v);
      setComments(c);
      setApprovals(a);
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Failed to load draft details");
    } finally {
      setLoading(false);
    }
  }, [collab.id, asset.id]);

  useEffect(() => {
    void load();
  }, [load]);

  const current = versions.find((v) => v.version === asset.current_version) ?? versions[0];
  const currentApprovals = approvals.filter((a) => a.version === asset.current_version);
  const myDecision = currentApprovals.find((a) => a.account_id === myAccountId)?.decision;
  const theirDecision = currentApprovals.find((a) => a.account_id !== myAccountId)?.decision;
  const ended = collab.state === "ended";

  async function doApprove() {
    setBusy(true);
    setError(null);
    try {
      await workspaceApi.approveAsset(collab.id, asset.id, note.trim() || undefined);
      setNotice("Approved.");
      setNote("");
      onChanged();
      await load();
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Failed to approve");
    } finally {
      setBusy(false);
    }
  }

  async function doRequestChanges() {
    setBusy(true);
    setError(null);
    try {
      await workspaceApi.requestAssetChanges(collab.id, asset.id, note.trim() || undefined);
      setNotice("Requested changes.");
      setNote("");
      onChanged();
      await load();
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Failed to request changes");
    } finally {
      setBusy(false);
    }
  }

  async function doComment() {
    if (!commentBody.trim()) return;
    setBusy(true);
    try {
      await workspaceApi.addAssetComment(collab.id, asset.id, commentBody.trim());
      setCommentBody("");
      await load();
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Failed to comment");
    } finally {
      setBusy(false);
    }
  }

  async function doRevise() {
    if (!reviseCaption.trim() && !reviseMedia.trim()) return;
    setBusy(true);
    try {
      await workspaceApi.addVersion(collab.id, asset.id, {
        caption: reviseCaption.trim() || undefined,
        media_urls: reviseMedia.trim() ? [reviseMedia.trim()] : [],
      });
      setNotice("New version proposed — approvals reset for both sides.");
      setShowRevise(false);
      setReviseCaption("");
      setReviseMedia("");
      onChanged();
      await load();
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Failed to revise");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="mt-3 space-y-3 border-t border-slate-200 pt-3">
      {error ? <div className="rounded-lg bg-red-50 px-3 py-2 text-sm text-red-700">{error}</div> : null}

      {loading ? (
        <Spinner />
      ) : (
        <>
          <div className="rounded-lg border border-slate-200 bg-slate-50 p-3">
            <p className="mb-1 text-xs text-slate-400">Version {asset.current_version} · current</p>
            {current?.caption ? <p className="text-sm text-slate-700">{current.caption}</p> : null}
            {current?.media_urls.map((u) => (
              <a key={u} href={u} target="_blank" rel="noreferrer" className="mt-1 block truncate text-xs text-brand underline">
                {u}
              </a>
            ))}
          </div>

          <div className="flex flex-wrap gap-3 text-xs text-slate-600">
            <span>You: <DecisionPill decision={myDecision} /></span>
            <span className="capitalize">{theirRoleLabel}: <DecisionPill decision={theirDecision} /></span>
          </div>

          {asset.state !== "published" && !ended ? (
            <div className="space-y-2">
              <input
                value={note}
                onChange={(e) => setNote(e.target.value)}
                placeholder="Optional note with your decision…"
                className={INPUT}
              />
              <div className="flex flex-wrap gap-2">
                <Button onClick={() => void doApprove()} disabled={busy}>Approve</Button>
                <Button variant="secondary" onClick={() => void doRequestChanges()} disabled={busy}>
                  Request changes
                </Button>
                <Button variant="secondary" onClick={() => setShowRevise((s) => !s)} disabled={busy}>
                  Propose a revision
                </Button>
                {role === "creator" && asset.state === "approved" ? (
                  <Button onClick={() => setShowPublish(true)} disabled={busy}>
                    Publish
                  </Button>
                ) : null}
              </div>
            </div>
          ) : null}

          {asset.state === "published" ? (
            <p className="text-xs text-purple-700">
              Published — now flowing through the normal content/social approval and scheduling pipeline.
            </p>
          ) : null}

          {showRevise ? (
            <div className="space-y-2 rounded-lg border border-slate-200 p-3">
              <label className={LABEL}>New caption</label>
              <textarea value={reviseCaption} onChange={(e) => setReviseCaption(e.target.value)} rows={3} className={INPUT} />
              {asset.kind !== "text" ? (
                <>
                  <label className={LABEL}>New media URL</label>
                  <input value={reviseMedia} onChange={(e) => setReviseMedia(e.target.value)} className={INPUT} />
                </>
              ) : null}
              <div className="flex justify-end gap-2">
                <Button variant="secondary" onClick={() => setShowRevise(false)}>Cancel</Button>
                <Button onClick={() => void doRevise()} disabled={busy}>Save as new version</Button>
              </div>
            </div>
          ) : null}

          {versions.length > 1 ? (
            <details className="text-xs text-slate-500">
              <summary className="cursor-pointer">Version history ({versions.length})</summary>
              <div className="mt-2 space-y-1.5">
                {versions.map((v) => (
                  <div key={v.id} className="border-b border-slate-100 pb-1.5 last:border-0">
                    <p className="font-medium">v{v.version} · {new Date(v.created_at).toLocaleString()}</p>
                    {v.caption ? <p>{v.caption}</p> : null}
                  </div>
                ))}
              </div>
            </details>
          ) : null}

          <div>
            <p className="mb-1 text-xs font-medium text-slate-500">Comments</p>
            <div className="mb-2 max-h-40 space-y-1.5 overflow-y-auto">
              {comments.length === 0 ? (
                <p className="text-xs text-slate-400">No comments yet.</p>
              ) : (
                comments.map((c) => (
                  <div key={c.id} className="rounded-lg bg-slate-50 px-2 py-1.5 text-xs">
                    <p className="text-slate-700">{c.body}</p>
                    <p className="text-slate-400">{new Date(c.created_at).toLocaleString()}</p>
                  </div>
                ))
              )}
            </div>
            {!ended ? (
              <div className="flex gap-2">
                <input
                  value={commentBody}
                  onChange={(e) => setCommentBody(e.target.value)}
                  onKeyDown={(e) => e.key === "Enter" && void doComment()}
                  placeholder="Add a comment…"
                  className={INPUT}
                />
                <Button variant="secondary" onClick={() => void doComment()} disabled={busy}>Send</Button>
              </div>
            ) : null}
          </div>
        </>
      )}

      {showPublish ? (
        <PublishModal
          collab={collab}
          asset={asset}
          myBrands={myBrands}
          onClose={() => setShowPublish(false)}
          onPublished={() => {
            setNotice("Published! It's now in your Social page for scheduling.");
            setShowPublish(false);
            onChanged();
            void load();
          }}
        />
      ) : null}
    </div>
  );
}

function DecisionPill({ decision }: { decision?: string }) {
  if (!decision) return <span className="text-slate-400">pending</span>;
  if (decision === "approved") return <span className="font-medium text-green-600">approved</span>;
  return <span className="font-medium text-amber-600">changes requested</span>;
}

function PublishModal({
  collab, asset, myBrands, onClose, onPublished,
}: {
  collab: Collaboration;
  asset: CollaborationAsset;
  myBrands: Brand[];
  onClose: () => void;
  onPublished: () => void;
}) {
  const [brandId, setBrandId] = useState(myBrands[0]?.id ?? "");
  const [platform, setPlatform] = useState("instagram");
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function publish() {
    if (!brandId) return;
    setSaving(true);
    setError(null);
    try {
      await workspaceApi.publishAsset(collab.id, asset.id, brandId, platform);
      onPublished();
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Failed to publish");
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className="fixed inset-0 z-50 flex items-start justify-center overflow-y-auto bg-black/40 p-4 sm:p-8" onClick={onClose}>
      <div className="w-full max-w-sm rounded-xl bg-white p-6 shadow-xl" onClick={(e) => e.stopPropagation()}>
        <h2 className="mb-3 text-lg font-semibold text-slate-800">Publish this draft</h2>
        <p className="mb-3 text-xs text-slate-500">
          Creates a post in your Social page under the brand and platform you choose — it still
          goes through your normal approval and scheduling from there.
        </p>
        {error ? <div className="mb-3 rounded-lg bg-red-50 px-3 py-2 text-sm text-red-700">{error}</div> : null}
        {myBrands.length === 0 ? (
          <p className="text-sm text-amber-600">You need a brand set up first — create one under Brands.</p>
        ) : (
          <div className="space-y-3">
            <div>
              <label className={LABEL}>Your brand</label>
              <select value={brandId} onChange={(e) => setBrandId(e.target.value)} className={INPUT}>
                {myBrands.map((b) => <option key={b.id} value={b.id}>{b.name}</option>)}
              </select>
            </div>
            <div>
              <label className={LABEL}>Platform</label>
              <select value={platform} onChange={(e) => setPlatform(e.target.value)} className={INPUT}>
                {PLATFORMS.map((p) => <option key={p} value={p}>{platformLabel(p)}</option>)}
              </select>
            </div>
            <div className="flex justify-end gap-2 pt-1">
              <Button type="button" variant="secondary" onClick={onClose}>Cancel</Button>
              <Button type="button" onClick={() => void publish()} disabled={saving || !brandId}>
                {saving ? "Publishing…" : "Publish"}
              </Button>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
