"use client";

import { useCallback, useEffect, useRef, useState } from "react";

import { PageHeader } from "@/components/PageHeader";
import { Button } from "@/components/ui/Button";
import { Card } from "@/components/ui/Card";
import { Spinner } from "@/components/ui/Spinner";
import { ApiError } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { useBrand } from "@/lib/brand";
import { mediaApi } from "@/lib/resources";
import type { MediaAsset } from "@/lib/types";

const PLATFORMS = ["instagram", "tiktok", "youtube", "facebook", "twitter", "linkedin"];

export default function MediaPage() {
  const { user } = useAuth();
  const { selectedBrandId } = useBrand();
  const canEdit = user ? user.role !== "viewer" : false;

  const [assets, setAssets] = useState<MediaAsset[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [enhance, setEnhance] = useState(true);
  const [open, setOpen] = useState<MediaAsset | null>(null);
  const fileRef = useRef<HTMLInputElement>(null);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      setAssets(await mediaApi.list(selectedBrandId));
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Failed to load media");
    } finally {
      setLoading(false);
    }
  }, [selectedBrandId]);

  useEffect(() => {
    void load();
  }, [load]);

  async function onUpload(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0];
    if (!file || !selectedBrandId) return;
    setBusy(true);
    setError(null);
    try {
      await mediaApi.upload(file, selectedBrandId);
      await load();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Upload failed");
    } finally {
      setBusy(false);
      if (fileRef.current) fileRef.current.value = "";
    }
  }

  async function process(id: string) {
    setBusy(true);
    setError(null);
    try {
      await mediaApi.process(id, [], enhance); // empty = all applicable platforms
      setOpen(await mediaApi.get(id));
      await load();
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Processing failed");
    } finally {
      setBusy(false);
    }
  }

  async function openDetail(id: string) {
    setOpen(await mediaApi.get(id));
  }

  async function approve(variantId: string, assetId: string) {
    await mediaApi.approveVariant(variantId);
    setOpen(await mediaApi.get(assetId));
  }

  return (
    <>
      <PageHeader
        title="Media"
        description="Upload once → generate platform-ready renditions. The original is always preserved."
      />

      {error ? (
        <div className="mb-4 rounded-lg bg-red-50 px-3 py-2 text-sm text-red-700">{error}</div>
      ) : null}

      {canEdit ? (
        <Card className="mb-6">
          {selectedBrandId ? (
            <div className="flex flex-wrap items-center gap-4">
              <input
                ref={fileRef}
                type="file"
                accept="image/*,video/*"
                onChange={onUpload}
                className="hidden"
              />
              <Button disabled={busy} onClick={() => fileRef.current?.click()}>
                {busy ? "Working…" : "Upload image / video"}
              </Button>
              <label className="flex items-center gap-2 text-sm text-slate-600">
                <input
                  type="checkbox"
                  checked={enhance}
                  onChange={(e) => setEnhance(e.target.checked)}
                />
                Enhance (auto-contrast + sharpen)
              </label>
            </div>
          ) : (
            <p className="text-sm text-slate-500">Select a brand in the top bar to upload media.</p>
          )}
        </Card>
      ) : null}

      {loading ? (
        <Spinner />
      ) : assets.length === 0 ? (
        <Card>
          <p className="text-sm text-slate-400">No media yet.</p>
        </Card>
      ) : (
        <div className="space-y-3">
          {assets.map((a) => (
            <Card key={a.id}>
              <div className="flex flex-wrap items-center justify-between gap-2">
                <button type="button" className="flex items-center gap-3 text-left" onClick={() => void openDetail(a.id)}>
                  <span className="flex h-12 w-12 shrink-0 items-center justify-center overflow-hidden rounded bg-slate-100">
                    {a.kind === "video" ? (
                      <video
                        src={`/api/media/${a.id}/original`}
                        preload="metadata"
                        muted
                        className="h-full w-full object-cover"
                      />
                    ) : (
                      // eslint-disable-next-line @next/next/no-img-element
                      <img
                        src={`/api/media/${a.id}/original`}
                        loading="lazy"
                        alt={a.original_filename}
                        className="h-full w-full object-cover"
                      />
                    )}
                  </span>
                  <span>
                    <span className="font-medium text-slate-800">{a.original_filename}</span>
                    <span className="ml-2 text-xs text-slate-400">
                      {a.kind} · {a.width}×{a.height} · {a.status}
                    </span>
                  </span>
                </button>
                {canEdit ? (
                  <div className="flex items-center gap-3">
                    <a
                      href={`/api/media/${a.id}/original`}
                      className="text-xs text-brand underline"
                    >
                      Original
                    </a>
                    <Button variant="secondary" disabled={busy} onClick={() => void process(a.id)}>
                      Generate renditions
                    </Button>
                  </div>
                ) : null}
              </div>

              {open?.id === a.id && (open.variants ?? []).length > 0 ? (
                <div className="mt-3 grid grid-cols-1 gap-2 border-t border-slate-100 pt-3 sm:grid-cols-2 lg:grid-cols-3">
                  {(open.variants ?? []).map((v) => (
                    <div key={v.id} className="rounded-lg border border-slate-200 p-2 text-xs">
                      <div className="mb-2 flex min-h-24 items-center justify-center overflow-hidden rounded bg-slate-50">
                        {v.format === "mp4" ? (
                          <video
                            src={`/api/media/variants/${v.id}/file`}
                            controls
                            preload="metadata"
                            className="max-h-40 w-full object-contain"
                          />
                        ) : (
                          // eslint-disable-next-line @next/next/no-img-element
                          <img
                            src={`/api/media/variants/${v.id}/file`}
                            loading="lazy"
                            alt={`${v.platform} ${v.purpose} rendition`}
                            className="max-h-40 w-full object-contain"
                          />
                        )}
                      </div>
                      <p className="font-medium text-slate-700">
                        {v.platform} · {v.purpose}
                      </p>
                      <p className="text-slate-400">
                        {v.width}×{v.height} ({v.aspect_ratio})
                      </p>
                      <div className="mt-1 flex items-center justify-between">
                        <a
                          href={`/api/media/variants/${v.id}/file`}
                          className="text-brand underline"
                        >
                          Download
                        </a>
                        {v.state === "approved" ? (
                          <span className="text-green-600">approved</span>
                        ) : canEdit ? (
                          <button
                            type="button"
                            className="text-slate-500 underline"
                            onClick={() => void approve(v.id, a.id)}
                          >
                            Approve
                          </button>
                        ) : null}
                      </div>
                    </div>
                  ))}
                </div>
              ) : null}
            </Card>
          ))}
        </div>
      )}
    </>
  );
}
