"use client";

import { useCallback, useEffect, useState } from "react";

import { Button } from "@/components/ui/Button";
import { Card, CardTitle } from "@/components/ui/Card";
import { Spinner } from "@/components/ui/Spinner";
import { ApiError } from "@/lib/api";
import { workspaceApi } from "@/lib/resources";
import type { Collaboration, Deliverable, DeliverableStatus } from "@/lib/types";

const STATUS_STYLE: Record<DeliverableStatus, string> = {
  pending: "bg-slate-100 text-slate-500",
  in_progress: "bg-blue-100 text-blue-700",
  delivered: "bg-amber-100 text-amber-700",
  approved: "bg-green-100 text-green-700",
};

const NEXT_STATUS: Record<DeliverableStatus, DeliverableStatus | null> = {
  pending: "in_progress",
  in_progress: "delivered",
  delivered: "approved",
  approved: null,
};

const NEXT_LABEL: Record<DeliverableStatus, string> = {
  pending: "Start",
  in_progress: "Mark delivered",
  delivered: "Approve",
  approved: "",
};

const INPUT =
  "w-full rounded-lg border border-slate-300 px-3 py-2 text-sm focus:border-brand focus:outline-none focus:ring-1 focus:ring-brand";
const LABEL = "mb-1 block text-xs font-medium text-slate-500";

export function DeliverablesPanel({ collab }: { collab: Collaboration }) {
  const [items, setItems] = useState<Deliverable[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [busyId, setBusyId] = useState<string | null>(null);
  const [showNew, setShowNew] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      setItems(await workspaceApi.listDeliverables(collab.id));
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Failed to load deliverables");
    } finally {
      setLoading(false);
    }
  }, [collab.id]);

  useEffect(() => {
    void load();
  }, [load]);

  const ended = collab.state === "ended";

  async function advance(d: Deliverable) {
    const next = NEXT_STATUS[d.status];
    if (!next) return;
    setBusyId(d.id);
    try {
      await workspaceApi.updateDeliverable(collab.id, d.id, { status: next });
      await load();
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Failed to update");
    } finally {
      setBusyId(null);
    }
  }

  return (
    <Card>
      <div className="mb-2 flex items-center justify-between">
        <CardTitle>Deliverables</CardTitle>
        {!ended ? (
          <Button variant="secondary" onClick={() => setShowNew(true)}>Add deliverable</Button>
        ) : null}
      </div>

      {error ? <div className="mb-3 rounded-lg bg-red-50 px-3 py-2 text-sm text-red-700">{error}</div> : null}

      {loading ? (
        <Spinner />
      ) : items.length === 0 ? (
        <p className="text-sm text-slate-400">No deliverables tracked yet.</p>
      ) : (
        <div className="space-y-2">
          {items.map((d) => {
            const next = NEXT_STATUS[d.status];
            return (
              <div key={d.id} className="flex items-center justify-between gap-2 rounded-lg border border-slate-200 px-3 py-2">
                <div>
                  <p className="text-sm font-medium text-slate-800">{d.title}</p>
                  {d.description ? <p className="text-xs text-slate-500">{d.description}</p> : null}
                  <p className="text-xs text-slate-400">
                    {d.due_at ? `Due ${new Date(d.due_at).toLocaleDateString()}` : "No due date"}
                    {d.asset_id ? " · linked to a draft" : ""}
                  </p>
                </div>
                <div className="flex items-center gap-2">
                  <span className={`rounded-full px-2 py-0.5 text-xs font-medium ${STATUS_STYLE[d.status]}`}>
                    {d.status.replace(/_/g, " ")}
                  </span>
                  {next && !ended ? (
                    <Button variant="secondary" onClick={() => void advance(d)} disabled={busyId === d.id}>
                      {NEXT_LABEL[d.status]}
                    </Button>
                  ) : null}
                </div>
              </div>
            );
          })}
        </div>
      )}

      {showNew ? (
        <NewDeliverableModal
          collab={collab}
          onClose={() => setShowNew(false)}
          onCreated={() => { setShowNew(false); void load(); }}
        />
      ) : null}
    </Card>
  );
}

function NewDeliverableModal({
  collab, onClose, onCreated,
}: { collab: Collaboration; onClose: () => void; onCreated: () => void }) {
  const [title, setTitle] = useState("");
  const [description, setDescription] = useState("");
  const [dueAt, setDueAt] = useState("");
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const canSave = title.trim().length > 0 && !saving;

  async function save() {
    if (!canSave) return;
    setSaving(true);
    setError(null);
    try {
      await workspaceApi.createDeliverable(collab.id, {
        title: title.trim(),
        description: description.trim() || undefined,
        due_at: dueAt ? new Date(`${dueAt}T00:00:00Z`).toISOString() : undefined,
      });
      onCreated();
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Failed to add deliverable");
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className="fixed inset-0 z-50 flex items-start justify-center overflow-y-auto bg-black/40 p-4 sm:p-8" onClick={onClose}>
      <div className="w-full max-w-sm rounded-xl bg-white p-6 shadow-xl" onClick={(e) => e.stopPropagation()}>
        <h2 className="mb-3 text-lg font-semibold text-slate-800">Add a deliverable</h2>
        {error ? <div className="mb-3 rounded-lg bg-red-50 px-3 py-2 text-sm text-red-700">{error}</div> : null}
        <div className="space-y-3">
          <div>
            <label className={LABEL}>Title *</label>
            <input value={title} onChange={(e) => setTitle(e.target.value)} placeholder="3 posts + 1 reel" className={INPUT} />
          </div>
          <div>
            <label className={LABEL}>Description</label>
            <textarea value={description} onChange={(e) => setDescription(e.target.value)} rows={2} className={INPUT} />
          </div>
          <div>
            <label className={LABEL}>Due date</label>
            <input type="date" value={dueAt} onChange={(e) => setDueAt(e.target.value)} className={INPUT} />
          </div>
          <div className="flex justify-end gap-2 pt-1">
            <Button type="button" variant="secondary" onClick={onClose}>Cancel</Button>
            <Button type="button" onClick={() => void save()} disabled={!canSave}>
              {saving ? "Saving…" : "Add"}
            </Button>
          </div>
        </div>
      </div>
    </div>
  );
}
