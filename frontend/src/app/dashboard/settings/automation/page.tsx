"use client";

import { useEffect, useState } from "react";

import { PageHeader } from "@/components/PageHeader";
import { Button } from "@/components/ui/Button";
import { Card, CardTitle } from "@/components/ui/Card";
import { Spinner } from "@/components/ui/Spinner";
import { ApiError, automationApi, type AutoApproveStatus } from "@/lib/api";
import { useAuth } from "@/lib/auth";

const DURATIONS: { label: string; hours: number | null }[] = [
  { label: "1 day", hours: 24 },
  { label: "3 days", hours: 72 },
  { label: "1 week", hours: 168 },
  { label: "2 weeks", hours: 336 },
  { label: "Until I turn it off", hours: null },
];

function fmt(iso: string | null) {
  if (!iso) return null;
  return new Date(iso).toLocaleString(undefined, {
    dateStyle: "medium",
    timeStyle: "short",
  });
}

export default function AutomationPage() {
  const { user } = useAuth();
  const isOwner = user?.role === "owner";

  const [status, setStatus] = useState<AutoApproveStatus | null>(null);
  const [loading, setLoading] = useState(true);
  const [working, setWorking] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [duration, setDuration] = useState<number | null>(24);
  const [acknowledged, setAcknowledged] = useState(false);

  useEffect(() => {
    automationApi
      .getAutoApprove()
      .then(setStatus)
      .catch((e) => setError(e instanceof ApiError ? e.message : "Failed to load"))
      .finally(() => setLoading(false));
  }, []);

  async function enable() {
    setWorking(true);
    setError(null);
    try {
      setStatus(await automationApi.setAutoApprove(true, duration));
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Could not enable auto-approve");
    } finally {
      setWorking(false);
    }
  }

  async function disable() {
    setWorking(true);
    setError(null);
    try {
      setStatus(await automationApi.setAutoApprove(false, null));
      setAcknowledged(false);
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Could not disable auto-approve");
    } finally {
      setWorking(false);
    }
  }

  return (
    <>
      <PageHeader
        title="Automation"
        description="Run hands-off. Auto-approve keeps your marketing engine publishing while you're away."
      />

      {error ? (
        <div className="mb-4 rounded-lg bg-red-50 px-3 py-2 text-sm text-red-700">{error}</div>
      ) : null}

      {loading || !status ? (
        <Spinner />
      ) : !isOwner ? (
        <Card>
          <p className="text-sm text-slate-500">
            Only the account owner can change auto-approve settings.
          </p>
        </Card>
      ) : (
        <div className="max-w-2xl space-y-4">
          {/* Current state */}
          <Card>
            <CardTitle>Auto-approve</CardTitle>
            {status.enabled ? (
              <div className="rounded-lg bg-green-50 border border-green-200 px-4 py-3 text-sm text-green-800">
                <strong>On</strong>
                {status.indefinite
                  ? " — indefinitely, until you turn it off."
                  : ` — until ${fmt(status.until)}.`}
                <p className="mt-1 text-green-700">
                  Approvals are being published automatically without review.
                </p>
              </div>
            ) : (
              <div className="rounded-lg bg-slate-50 border border-slate-200 px-4 py-3 text-sm text-slate-600">
                <strong>Off</strong> — every post and send waits for your manual approval.
              </div>
            )}
          </Card>

          {/* The honest warning + controls */}
          {status.enabled ? (
            <Card>
              <Button variant="danger" onClick={() => void disable()} disabled={working}>
                {working ? "Turning off…" : "Turn off auto-approve"}
              </Button>
              <p className="mt-2 text-xs text-slate-400">
                Turning it off restores manual approval for everything pending.
              </p>
            </Card>
          ) : (
            <Card>
              <div className="mb-3 rounded-lg bg-amber-50 border border-amber-200 px-4 py-3 text-sm text-amber-800">
                <p className="font-semibold">⚠️ AI can make mistakes.</p>
                <p className="mt-1">
                  With auto-approve on, drafts and scheduled posts publish to your connected
                  accounts <strong>without human review</strong>. Content is still generated
                  on-brand and passes quality checks, but occasional errors can slip through.
                  Use this when you want the system to keep working while you&apos;re on vacation
                  or hands-off — and turn it back off when you want the final say.
                </p>
              </div>

              <label className="mb-1 block text-sm font-medium text-slate-700">
                Keep auto-approve on for
              </label>
              <select
                value={duration === null ? "null" : String(duration)}
                onChange={(e) =>
                  setDuration(e.target.value === "null" ? null : Number(e.target.value))
                }
                className="mb-3 w-full rounded-lg border border-slate-300 px-3 py-2 text-sm"
              >
                {DURATIONS.map((d) => (
                  <option key={d.label} value={d.hours === null ? "null" : String(d.hours)}>
                    {d.label}
                  </option>
                ))}
              </select>

              <label className="mb-3 flex items-start gap-2 text-sm text-slate-600">
                <input
                  type="checkbox"
                  checked={acknowledged}
                  onChange={(e) => setAcknowledged(e.target.checked)}
                  className="mt-0.5"
                />
                I understand posts will publish automatically without my review, and that AI
                can occasionally make mistakes.
              </label>

              <Button onClick={() => void enable()} disabled={working || !acknowledged}>
                {working ? "Enabling…" : "Enable auto-approve"}
              </Button>
            </Card>
          )}
        </div>
      )}
    </>
  );
}
