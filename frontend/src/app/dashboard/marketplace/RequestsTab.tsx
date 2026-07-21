"use client";

import { useCallback, useEffect, useState } from "react";

import { Button } from "@/components/ui/Button";
import { Card } from "@/components/ui/Card";
import { Spinner } from "@/components/ui/Spinner";
import { ApiError } from "@/lib/api";
import { marketplaceApi } from "@/lib/resources";
import type { CollaborationRequest, MatchCreator, MatchProduct } from "@/lib/types";

type Box = "incoming" | "outgoing";

const STATUS_STYLE: Record<string, string> = {
  pending: "bg-amber-100 text-amber-700",
  accepted: "bg-green-100 text-green-700",
  declined: "bg-red-100 text-red-700",
  withdrawn: "bg-slate-100 text-slate-500",
  expired: "bg-slate-100 text-slate-500",
};

export function RequestsTab({ setNotice }: { setNotice: (s: string | null) => void }) {
  const [box, setBox] = useState<Box>("incoming");
  const [requests, setRequests] = useState<CollaborationRequest[]>([]);
  const [myCreators, setMyCreators] = useState<MatchCreator[]>([]);
  const [myProducts, setMyProducts] = useState<MatchProduct[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [busyId, setBusyId] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const [reqs, creators, products] = await Promise.all([
        marketplaceApi.collaborations(box),
        marketplaceApi.myCreators({ limit: "100" }),
        marketplaceApi.myProducts({ limit: "100" }),
      ]);
      setRequests(reqs);
      setMyCreators(creators);
      setMyProducts(products);
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Failed to load requests");
    } finally {
      setLoading(false);
    }
  }, [box]);

  useEffect(() => {
    void load();
  }, [load]);

  function creatorName(id: string): string {
    return myCreators.find((c) => c.id === id)?.display_name ?? "a creator";
  }
  function productName(id: string | null | undefined): string {
    if (!id) return "a product";
    return myProducts.find((p) => p.id === id)?.name ?? "a product";
  }

  function describe(req: CollaborationRequest): string {
    const brandSide = req.direction === "brand_to_creator";
    // Best-effort: resolve names only when the party is in your own roster —
    // the other tenant's identity isn't exposed pre-acceptance.
    if (box === "incoming") {
      return brandSide
        ? `A brand wants to work with ${creatorName(req.creator_id)}`
        : `${creatorName(req.creator_id) === "a creator" ? "A creator" : creatorName(req.creator_id)} wants to work with ${productName(req.product_id)}`;
    }
    return brandSide
      ? `You reached out about ${productName(req.product_id)} to a creator`
      : `${creatorName(req.creator_id)} reached out to a brand`;
  }

  async function respond(req: CollaborationRequest, accept: boolean) {
    setBusyId(req.id);
    setError(null);
    try {
      await marketplaceApi.respond(req.id, accept);
      setNotice(accept ? "Request accepted." : "Request declined.");
      await load();
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Failed to respond");
    } finally {
      setBusyId(null);
    }
  }

  async function withdraw(req: CollaborationRequest) {
    setBusyId(req.id);
    setError(null);
    try {
      await marketplaceApi.withdraw(req.id);
      setNotice("Request withdrawn.");
      await load();
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Failed to withdraw");
    } finally {
      setBusyId(null);
    }
  }

  return (
    <>
      {error ? (
        <div className="mb-4 rounded-lg bg-red-50 px-3 py-2 text-sm text-red-700">{error}</div>
      ) : null}

      <div className="mb-4 flex gap-2">
        {(["incoming", "outgoing"] as Box[]).map((b) => (
          <button
            key={b}
            type="button"
            onClick={() => setBox(b)}
            className={`rounded-lg px-3 py-1.5 text-sm font-medium capitalize ${
              box === b ? "bg-brand text-white" : "border border-slate-200 bg-white text-slate-600"
            }`}
          >
            {b}
          </button>
        ))}
      </div>

      {loading ? (
        <Spinner />
      ) : requests.length === 0 ? (
        <Card>
          <p className="text-sm text-slate-400">
            {box === "incoming" ? "No requests waiting on you." : "You haven't sent any requests yet."}
          </p>
        </Card>
      ) : (
        <div className="space-y-3">
          {requests.map((req) => (
            <Card key={req.id}>
              <div className="flex items-start justify-between gap-3">
                <div>
                  <div className="mb-1 flex items-center gap-2">
                    <span className={`rounded-full px-2 py-0.5 text-xs font-medium ${STATUS_STYLE[req.status]}`}>
                      {req.status}
                    </span>
                    <span className="text-xs text-slate-400">
                      {new Date(req.created_at).toLocaleDateString()}
                    </span>
                  </div>
                  <p className="text-sm font-medium text-slate-800">{describe(req)}</p>
                  <p className="mt-1 text-sm text-slate-600">{req.message}</p>
                  {req.response_note ? (
                    <p className="mt-1 text-xs italic text-slate-500">“{req.response_note}”</p>
                  ) : null}
                </div>
                {req.status === "pending" ? (
                  <div className="flex shrink-0 gap-2">
                    {box === "incoming" ? (
                      <>
                        <Button
                          variant="secondary"
                          disabled={busyId === req.id}
                          onClick={() => void respond(req, false)}
                        >
                          Decline
                        </Button>
                        <Button disabled={busyId === req.id} onClick={() => void respond(req, true)}>
                          Accept
                        </Button>
                      </>
                    ) : (
                      <Button
                        variant="secondary"
                        disabled={busyId === req.id}
                        onClick={() => void withdraw(req)}
                      >
                        Withdraw
                      </Button>
                    )}
                  </div>
                ) : null}
              </div>
            </Card>
          ))}
        </div>
      )}
    </>
  );
}
