"use client";

import { useCallback, useEffect, useState } from "react";

import { Button } from "@/components/ui/Button";
import { Card, CardTitle } from "@/components/ui/Card";
import { Spinner } from "@/components/ui/Spinner";
import { ApiError } from "@/lib/api";
import { workspaceApi } from "@/lib/resources";
import type { Collaboration, CollaborationBrief } from "@/lib/types";

const INPUT =
  "w-full rounded-lg border border-slate-300 px-3 py-2 text-sm focus:border-brand focus:outline-none focus:ring-1 focus:ring-brand";
const LABEL = "mb-1 block text-xs font-medium text-slate-500";

function linesToList(s: string): string[] {
  return s.split("\n").map((l) => l.trim()).filter(Boolean);
}

export function BriefPanel({ collab }: { collab: Collaboration }) {
  const [brief, setBrief] = useState<CollaborationBrief | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [editing, setEditing] = useState(false);
  const [saving, setSaving] = useState(false);

  const [goals, setGoals] = useState("");
  const [keyMessages, setKeyMessages] = useState("");
  const [dos, setDos] = useState("");
  const [donts, setDonts] = useState("");
  const [deadline, setDeadline] = useState("");
  const [requiresDisclosure, setRequiresDisclosure] = useState(true);
  const [disclosureText, setDisclosureText] = useState("#ad");
  const [usageRights, setUsageRights] = useState("");
  const [usageDurationDays, setUsageDurationDays] = useState("");
  const [whitelistingAllowed, setWhitelistingAllowed] = useState(false);
  const [boostAllowed, setBoostAllowed] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const b = await workspaceApi.getBrief(collab.id);
      setBrief(b);
      if (b) {
        setGoals(b.goals ?? "");
        setKeyMessages(b.key_messages.join("\n"));
        setDos(b.dos.join("\n"));
        setDonts(b.donts.join("\n"));
        setDeadline(b.deadline ? b.deadline.slice(0, 10) : "");
        setRequiresDisclosure(b.requires_disclosure);
        setDisclosureText(b.disclosure_text ?? "#ad");
        setUsageRights(b.usage_rights ?? "");
        setUsageDurationDays(b.usage_duration_days != null ? String(b.usage_duration_days) : "");
        setWhitelistingAllowed(b.whitelisting_allowed);
        setBoostAllowed(b.boost_allowed);
      }
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Failed to load the brief");
    } finally {
      setLoading(false);
    }
  }, [collab.id]);

  useEffect(() => {
    void load();
  }, [load]);

  const ended = collab.state === "ended";

  async function save() {
    setSaving(true);
    setError(null);
    try {
      await workspaceApi.upsertBrief(collab.id, {
        goals: goals.trim() || undefined,
        key_messages: linesToList(keyMessages),
        dos: linesToList(dos),
        donts: linesToList(donts),
        deadline: deadline ? new Date(`${deadline}T00:00:00Z`).toISOString() : undefined,
        requires_disclosure: requiresDisclosure,
        disclosure_text: disclosureText.trim() || undefined,
        usage_rights: usageRights.trim() || undefined,
        usage_duration_days: usageDurationDays ? Number(usageDurationDays) : undefined,
        whitelisting_allowed: whitelistingAllowed,
        boost_allowed: boostAllowed,
      });
      setEditing(false);
      await load();
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Failed to save the brief");
    } finally {
      setSaving(false);
    }
  }

  return (
    <Card>
      <div className="mb-2 flex items-center justify-between">
        <CardTitle>Brief</CardTitle>
        {!editing && !ended ? (
          <Button variant="secondary" onClick={() => setEditing(true)}>
            {brief ? "Edit" : "Create brief"}
          </Button>
        ) : null}
      </div>
      <p className="mb-3 text-xs text-slate-500">
        Shared and co-authored — either side can edit. Agree on goals, disclosure, and usage rights
        up front so nothing's a surprise once content goes live.
      </p>

      {error ? <div className="mb-3 rounded-lg bg-red-50 px-3 py-2 text-sm text-red-700">{error}</div> : null}

      {loading ? (
        <Spinner />
      ) : editing ? (
        <div className="space-y-3">
          <div>
            <label className={LABEL}>Goals</label>
            <textarea value={goals} onChange={(e) => setGoals(e.target.value)} rows={2} className={INPUT} />
          </div>
          <div className="grid grid-cols-1 gap-3 sm:grid-cols-3">
            <div>
              <label className={LABEL}>Key messages (one per line)</label>
              <textarea value={keyMessages} onChange={(e) => setKeyMessages(e.target.value)} rows={3} className={INPUT} />
            </div>
            <div>
              <label className={LABEL}>Do's (one per line)</label>
              <textarea value={dos} onChange={(e) => setDos(e.target.value)} rows={3} className={INPUT} />
            </div>
            <div>
              <label className={LABEL}>Don'ts (one per line)</label>
              <textarea value={donts} onChange={(e) => setDonts(e.target.value)} rows={3} className={INPUT} />
            </div>
          </div>
          <div>
            <label className={LABEL}>Deadline</label>
            <input type="date" value={deadline} onChange={(e) => setDeadline(e.target.value)} className={INPUT} />
          </div>

          <div className="rounded-lg border border-slate-200 bg-slate-50 p-3">
            <label className="flex items-center gap-2 text-sm text-slate-700">
              <input
                type="checkbox"
                checked={requiresDisclosure}
                onChange={(e) => setRequiresDisclosure(e.target.checked)}
              />
              Requires FTC disclosure (e.g. #ad)
            </label>
            {requiresDisclosure ? (
              <input
                value={disclosureText}
                onChange={(e) => setDisclosureText(e.target.value)}
                placeholder="#ad #sponsored"
                className={`${INPUT} mt-2`}
              />
            ) : null}
          </div>

          <div className="rounded-lg border border-slate-200 p-3">
            <label className={LABEL}>Usage / licensing rights</label>
            <textarea value={usageRights} onChange={(e) => setUsageRights(e.target.value)} rows={2} className={INPUT} />
            <div className="mt-2 grid grid-cols-1 gap-3 sm:grid-cols-3">
              <div>
                <label className={LABEL}>Duration (days, blank = unspecified)</label>
                <input
                  type="number"
                  min={0}
                  value={usageDurationDays}
                  onChange={(e) => setUsageDurationDays(e.target.value)}
                  className={INPUT}
                />
              </div>
              <label className="mt-5 flex items-center gap-2 text-sm text-slate-700">
                <input type="checkbox" checked={whitelistingAllowed} onChange={(e) => setWhitelistingAllowed(e.target.checked)} />
                Whitelisting allowed
              </label>
              <label className="mt-5 flex items-center gap-2 text-sm text-slate-700">
                <input type="checkbox" checked={boostAllowed} onChange={(e) => setBoostAllowed(e.target.checked)} />
                Paid boost allowed
              </label>
            </div>
          </div>

          <div className="flex justify-end gap-2">
            <Button type="button" variant="secondary" onClick={() => { setEditing(false); void load(); }}>
              Cancel
            </Button>
            <Button type="button" onClick={() => void save()} disabled={saving}>
              {saving ? "Saving…" : "Save brief"}
            </Button>
          </div>
        </div>
      ) : brief ? (
        <div className="space-y-2 text-sm">
          {brief.goals ? <p><span className="font-medium text-slate-600">Goals: </span>{brief.goals}</p> : null}
          {brief.key_messages.length > 0 ? (
            <p><span className="font-medium text-slate-600">Key messages: </span>{brief.key_messages.join(" · ")}</p>
          ) : null}
          {brief.dos.length > 0 ? <p><span className="font-medium text-slate-600">Do: </span>{brief.dos.join(" · ")}</p> : null}
          {brief.donts.length > 0 ? <p><span className="font-medium text-slate-600">Don't: </span>{brief.donts.join(" · ")}</p> : null}
          {brief.deadline ? (
            <p><span className="font-medium text-slate-600">Deadline: </span>{new Date(brief.deadline).toLocaleDateString()}</p>
          ) : null}
          <p>
            <span className="font-medium text-slate-600">Disclosure: </span>
            {brief.requires_disclosure ? `Required — "${brief.disclosure_text || "not specified"}"` : "Not required"}
          </p>
          {brief.usage_rights || brief.usage_duration_days != null ? (
            <p>
              <span className="font-medium text-slate-600">Usage rights: </span>
              {brief.usage_rights}
              {brief.usage_duration_days != null ? ` (${brief.usage_duration_days} days)` : ""}
              {brief.whitelisting_allowed ? " · whitelisting ok" : ""}
              {brief.boost_allowed ? " · boosting ok" : ""}
            </p>
          ) : null}
        </div>
      ) : (
        <p className="text-sm text-slate-400">No brief yet — either side can start one.</p>
      )}
    </Card>
  );
}
