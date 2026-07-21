"use client";

import { useCallback, useEffect, useState } from "react";

import { PageHeader } from "@/components/PageHeader";
import { Button } from "@/components/ui/Button";
import { Card } from "@/components/ui/Card";
import { Spinner } from "@/components/ui/Spinner";
import { ApiError } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { approvalsApi, socialCommentsApi } from "@/lib/resources";
import type { Approval } from "@/lib/types";

export default function ApprovalsPage() {
  const { user } = useAuth();
  const canDecide = user?.role === "admin" || user?.role === "owner";

  const [items, setItems] = useState<Approval[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [busy, setBusy] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      setItems(await approvalsApi.list());
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Failed to load approvals");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  async function approve(id: string) {
    setBusy(id);
    setError(null);
    try {
      const res = await approvalsApi.approve(id);
      setNotice(res.sent != null ? `Approved — ${res.sent} emails dispatched.` : "Approved.");
      await load();
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Approve failed");
    } finally {
      setBusy(null);
    }
  }

  async function likeComment(commentId: string) {
    setBusy(commentId);
    setError(null);
    try {
      await socialCommentsApi.like(commentId);
      setNotice("Liked the comment. 👍");
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Could not like the comment.");
    } finally {
      setBusy(null);
    }
  }

  async function reject(id: string) {
    const reason = prompt("Reason for rejection (optional):") ?? undefined;
    setBusy(id);
    try {
      await approvalsApi.reject(id, reason);
      setNotice("Rejected.");
      await load();
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Reject failed");
    } finally {
      setBusy(null);
    }
  }

  return (
    <>
      <PageHeader
        title="Approvals"
        description="Nothing goes out without a human OK. Review and approve bulk sends here."
      />

      {error ? (
        <div className="mb-4 rounded-lg bg-red-50 px-3 py-2 text-sm text-red-700">{error}</div>
      ) : null}
      {notice ? (
        <div className="mb-4 rounded-lg bg-green-50 px-3 py-2 text-sm text-green-700">{notice}</div>
      ) : null}

      {loading ? (
        <Spinner />
      ) : items.length === 0 ? (
        <Card>
          <p className="text-sm text-slate-400">Nothing awaiting approval. 🎉</p>
        </Card>
      ) : (
        <div className="space-y-4">
          {items.map((a) => (
            <Card key={a.id}>
              <div className="flex flex-wrap items-start justify-between gap-3">
                <div className="grow">
                  <span className="rounded-full bg-amber-100 px-2 py-0.5 text-xs font-medium text-amber-700">
                    {a.action_type.replace(/_/g, " ")}
                  </span>
                  <p className="mt-2 font-medium text-slate-800">{a.title}</p>
                  {a.summary ? <p className="text-sm text-slate-500">{a.summary}</p> : null}
                  {a.risk_notes ? (
                    <p className="mt-1 text-xs text-slate-400">{a.risk_notes}</p>
                  ) : null}
                </div>
                {canDecide ? (
                  <div className="flex flex-wrap gap-2">
                    <Button disabled={busy === a.id} onClick={() => void approve(a.id)}>
                      {a.action_type === "social_comment_reply" ? "Approve & post reply" : "Approve"}
                    </Button>
                    {/* Like the underlying comment (Facebook only — IG has no
                        like-comment API). Title carries the platform. */}
                    {a.action_type === "social_comment_reply" && a.entity_id && a.title.includes("Facebook") ? (
                      <Button
                        variant="secondary"
                        disabled={busy === a.entity_id}
                        onClick={() => void likeComment(a.entity_id!)}
                      >
                        👍 Like comment
                      </Button>
                    ) : null}
                    <Button
                      variant="danger"
                      disabled={busy === a.id}
                      onClick={() => void reject(a.id)}
                    >
                      Reject
                    </Button>
                  </div>
                ) : (
                  <span className="text-xs text-slate-400">Admin approval required</span>
                )}
              </div>
            </Card>
          ))}
        </div>
      )}
    </>
  );
}
