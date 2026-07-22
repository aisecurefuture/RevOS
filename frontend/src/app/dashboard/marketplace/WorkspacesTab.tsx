"use client";

import { useCallback, useEffect, useState } from "react";

import { Button } from "@/components/ui/Button";
import { Card, CardTitle } from "@/components/ui/Card";
import { Spinner } from "@/components/ui/Spinner";
import { ApiError } from "@/lib/api";
import { brandsApi, marketplaceApi, workspaceApi } from "@/lib/resources";
import type {
  Brand,
  Collaboration,
  CollaborationShare,
  MatchCreator,
  MatchProduct,
  SharedBrandBook,
} from "@/lib/types";

import { AssetsPanel } from "./AssetsPanel";
import { BriefPanel } from "./BriefPanel";
import { DeliverablesPanel } from "./DeliverablesPanel";
import { MessagesPanel } from "./MessagesPanel";

const STATE_STYLE: Record<string, string> = {
  active: "bg-green-100 text-green-700",
  paused: "bg-amber-100 text-amber-700",
  completed: "bg-blue-100 text-blue-700",
  ended: "bg-slate-100 text-slate-500",
};

const SHARE_STATUS_STYLE: Record<string, string> = {
  active: "bg-green-100 text-green-700",
  expired: "bg-amber-100 text-amber-700",
  revoked: "bg-slate-100 text-slate-500",
};

export function WorkspacesTab({ setNotice }: { setNotice: (s: string | null) => void }) {
  const [collabs, setCollabs] = useState<Collaboration[]>([]);
  const [myCreators, setMyCreators] = useState<MatchCreator[]>([]);
  const [myProducts, setMyProducts] = useState<MatchProduct[]>([]);
  const [myBrands, setMyBrands] = useState<Brand[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [selectedId, setSelectedId] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const [c, cr, p, b] = await Promise.all([
        workspaceApi.list(),
        marketplaceApi.myCreators({ limit: "100" }),
        marketplaceApi.myProducts({ limit: "100" }),
        brandsApi.list(),
      ]);
      setCollabs(c);
      setMyCreators(cr);
      setMyProducts(p);
      setMyBrands(b);
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Failed to load workspaces");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  const myCreatorIds = new Set(myCreators.map((c) => c.id));
  const roleFor = (c: Collaboration): "creator" | "brand" =>
    myCreatorIds.has(c.creator_id) ? "creator" : "brand";

  if (loading) return <Spinner />;

  const selected = collabs.find((c) => c.id === selectedId) ?? null;

  return (
    <div className="grid grid-cols-1 gap-4 lg:grid-cols-[minmax(0,1fr)_minmax(0,1.4fr)]">
      <div>
        {error ? (
          <div className="mb-4 rounded-lg bg-red-50 px-3 py-2 text-sm text-red-700">{error}</div>
        ) : null}
        {collabs.length === 0 ? (
          <Card>
            <p className="text-sm text-slate-400">
              No collaborations yet — they appear automatically once a request you sent or
              received is accepted.
            </p>
          </Card>
        ) : (
          <div className="space-y-2">
            {collabs.map((c) => {
              const role = roleFor(c);
              const label = role === "creator"
                ? myCreators.find((x) => x.id === c.creator_id)?.display_name ?? "Your creator"
                : myProducts.find((x) => x.id === c.product_id)?.name ?? "Your product";
              return (
                <Card
                  key={c.id}
                  className={`cursor-pointer py-3 ${selectedId === c.id ? "ring-2 ring-brand" : ""}`}
                  onClick={() => setSelectedId(c.id)}
                >
                  <div className="flex items-center justify-between gap-2">
                    <div>
                      <p className="text-sm font-medium text-slate-800">{label}</p>
                      <p className="text-xs text-slate-500">
                        You're the {role} · {new Date(c.created_at).toLocaleDateString()}
                      </p>
                    </div>
                    <span className={`rounded-full px-2 py-0.5 text-xs font-medium ${STATE_STYLE[c.state]}`}>
                      {c.state}
                    </span>
                  </div>
                </Card>
              );
            })}
          </div>
        )}
      </div>

      <div>
        {selected ? (
          <WorkspaceDetail
            key={selected.id}
            collab={selected}
            role={roleFor(selected)}
            myBrands={myBrands}
            myCreators={myCreators}
            myProducts={myProducts}
            setNotice={setNotice}
            onChanged={load}
          />
        ) : (
          <Card>
            <p className="text-sm text-slate-400">Select a collaboration to view its workspace.</p>
          </Card>
        )}
      </div>
    </div>
  );
}

function WorkspaceDetail({
  collab, role, myBrands, myCreators, myProducts, setNotice, onChanged,
}: {
  collab: Collaboration;
  role: "creator" | "brand";
  myBrands: Brand[];
  myCreators: MatchCreator[];
  myProducts: MatchProduct[];
  setNotice: (s: string | null) => void;
  onChanged: () => void;
}) {
  const [shares, setShares] = useState<CollaborationShare[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [busyId, setBusyId] = useState<string | null>(null);
  const [readBook, setReadBook] = useState<SharedBrandBook | null>(null);
  const [shareBrandId, setShareBrandId] = useState("");

  const myBrandIds = new Set(myBrands.map((b) => b.id));

  const linkedBrandId =
    role === "creator"
      ? myCreators.find((c) => c.id === collab.creator_id)?.brand_id
      : myProducts.find((p) => p.id === collab.product_id)?.brand_id;

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      setShares(await workspaceApi.shares(collab.id));
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Failed to load shares");
    } finally {
      setLoading(false);
    }
  }, [collab.id]);

  useEffect(() => {
    void load();
    setShareBrandId(linkedBrandId ?? myBrands[0]?.id ?? "");
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [load]);

  async function doShare() {
    if (!shareBrandId) return;
    setBusyId("share");
    setError(null);
    try {
      await workspaceApi.shareBrandBook(collab.id, shareBrandId);
      setNotice("Brand Book shared — the other side can now read it.");
      await load();
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Failed to share");
    } finally {
      setBusyId(null);
    }
  }

  async function doRevoke(shareId: string) {
    setBusyId(shareId);
    try {
      await workspaceApi.revokeShare(collab.id, shareId);
      setNotice("Access revoked.");
      await load();
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Failed to revoke");
    } finally {
      setBusyId(null);
    }
  }

  async function doRead(shareId: string) {
    setBusyId(shareId);
    setReadBook(null);
    try {
      setReadBook(await workspaceApi.readSharedBrandBook(collab.id, shareId));
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Failed to open — access may have expired.");
    } finally {
      setBusyId(null);
    }
  }

  async function doEnd() {
    if (!confirm("End this collaboration? All active shares will be revoked immediately.")) return;
    setBusyId("end");
    try {
      await workspaceApi.end(collab.id);
      setNotice("Collaboration ended — all shares revoked.");
      onChanged();
      await load();
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Failed to end");
    } finally {
      setBusyId(null);
    }
  }

  const canEnd = collab.state !== "ended";

  return (
    <div className="space-y-4">
      {error ? (
        <div className="rounded-lg bg-red-50 px-3 py-2 text-sm text-red-700">{error}</div>
      ) : null}

      <Card>
        <div className="flex items-center justify-between">
          <CardTitle>Workspace</CardTitle>
          {canEnd ? (
            <Button variant="secondary" onClick={() => void doEnd()} disabled={busyId === "end"}>
              {busyId === "end" ? "Ending…" : "End collaboration"}
            </Button>
          ) : null}
        </div>
        <p className="text-xs text-slate-500">
          State: <span className="font-medium">{collab.state}</span>
          {collab.ended_at ? ` · ended ${new Date(collab.ended_at).toLocaleDateString()}` : ""}
        </p>
      </Card>

      <Card>
        <CardTitle>Share your Brand Book</CardTitle>
        <p className="mb-2 text-xs text-slate-500">
          Consent-gated — only the other party can read it, you can revoke any time, and it's
          automatically revoked when this collaboration ends.
        </p>
        {myBrands.length === 0 ? (
          <p className="text-xs text-slate-400">
            You don't have a brand set up yet — create one under Brands first.
          </p>
        ) : (
          <div className="flex gap-2">
            <select
              value={shareBrandId}
              onChange={(e) => setShareBrandId(e.target.value)}
              className="grow rounded-lg border border-slate-300 px-3 py-2 text-sm"
            >
              {myBrands.map((b) => (
                <option key={b.id} value={b.id}>{b.name}</option>
              ))}
            </select>
            <Button onClick={() => void doShare()} disabled={busyId === "share" || collab.state === "ended"}>
              {busyId === "share" ? "Sharing…" : "Share"}
            </Button>
          </div>
        )}
      </Card>

      <MessagesPanel collab={collab} role={role} />

      <BriefPanel collab={collab} />

      <DeliverablesPanel collab={collab} />

      <AssetsPanel
        collab={collab}
        role={role}
        myBrands={myBrands}
        setNotice={setNotice}
      />

      <Card>
        <CardTitle>Shared with this collaboration</CardTitle>
        {loading ? (
          <Spinner />
        ) : shares.length === 0 ? (
          <p className="text-sm text-slate-400">Nothing shared yet.</p>
        ) : (
          <div className="space-y-2">
            {shares.map((s) => {
              const mine = myBrandIds.has(s.resource_id);
              return (
                <div key={s.id} className="flex items-center justify-between gap-2 border-b border-slate-100 py-2 last:border-0">
                  <div>
                    <p className="text-sm text-slate-700">
                      Brand Book · {mine ? "shared by you" : "shared with you"}
                    </p>
                    {s.expires_at ? (
                      <p className="text-xs text-slate-400">
                        Expires {new Date(s.expires_at).toLocaleDateString()}
                      </p>
                    ) : null}
                  </div>
                  <div className="flex items-center gap-2">
                    <span className={`rounded-full px-2 py-0.5 text-xs font-medium ${SHARE_STATUS_STYLE[s.status]}`}>
                      {s.status}
                    </span>
                    {s.status === "active" ? (
                      <Button
                        variant="secondary"
                        onClick={() => void doRead(s.id)}
                        disabled={busyId === s.id}
                      >
                        View
                      </Button>
                    ) : null}
                    {mine && s.status === "active" ? (
                      <Button
                        variant="secondary"
                        onClick={() => void doRevoke(s.id)}
                        disabled={busyId === s.id}
                      >
                        Revoke
                      </Button>
                    ) : null}
                  </div>
                </div>
              );
            })}
          </div>
        )}
      </Card>

      {readBook ? <BrandBookView book={readBook} onClose={() => setReadBook(null)} /> : null}
    </div>
  );
}

function BrandBookView({ book, onClose }: { book: SharedBrandBook; onClose: () => void }) {
  return (
    <div className="fixed inset-0 z-50 flex items-start justify-center overflow-y-auto bg-black/40 p-4 sm:p-8" onClick={onClose}>
      <div className="w-full max-w-lg rounded-xl bg-white p-6 shadow-xl" onClick={(e) => e.stopPropagation()}>
        <div className="mb-3 flex items-center justify-between">
          <h2 className="text-lg font-semibold text-slate-800">Shared Brand Book</h2>
          <button type="button" onClick={onClose} className="text-slate-400 hover:text-slate-600">✕</button>
        </div>
        <div className="space-y-3 text-sm">
          {book.elevator_pitch ? (
            <div><p className="text-xs font-medium text-slate-500">Elevator pitch</p><p className="text-slate-700">{book.elevator_pitch}</p></div>
          ) : null}
          {book.mission ? (
            <div><p className="text-xs font-medium text-slate-500">Mission</p><p className="text-slate-700">{book.mission}</p></div>
          ) : null}
          {book.positioning ? (
            <div><p className="text-xs font-medium text-slate-500">Positioning</p><p className="text-slate-700">{book.positioning}</p></div>
          ) : null}
          {book.target_summary ? (
            <div><p className="text-xs font-medium text-slate-500">Audience</p><p className="text-slate-700">{book.target_summary}</p></div>
          ) : null}
          {book.brand_story ? (
            <div><p className="text-xs font-medium text-slate-500">Brand story</p><p className="text-slate-700">{book.brand_story}</p></div>
          ) : null}
          {book.banned_terms.length > 0 ? (
            <div>
              <p className="text-xs font-medium text-slate-500">Never say</p>
              <p className="text-slate-700">{book.banned_terms.join(", ")}</p>
            </div>
          ) : null}
          {book.required_disclaimers.length > 0 ? (
            <div>
              <p className="text-xs font-medium text-slate-500">Required disclaimers</p>
              <p className="text-slate-700">{book.required_disclaimers.join(" · ")}</p>
            </div>
          ) : null}
          {!book.is_published ? (
            <p className="text-xs text-amber-600">This brand book is still a draft.</p>
          ) : null}
        </div>
      </div>
    </div>
  );
}
