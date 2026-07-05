"use client";

import { useCallback, useEffect, useState } from "react";

import { PageHeader } from "@/components/PageHeader";
import { Button } from "@/components/ui/Button";
import { Card, CardTitle } from "@/components/ui/Card";
import { Spinner } from "@/components/ui/Spinner";
import {
  ApiError,
  avatarApi,
  personaApi,
  type AvatarDuration,
  type AvatarJob,
  type PersonaConsent,
  type PersonaIdentity,
} from "@/lib/api";
import { useAuth } from "@/lib/auth";

function fmtWait(seconds: number): string {
  const m = Math.round(seconds / 60);
  if (m < 1) return "<1 min";
  if (m < 90) return `~${m} min`;
  return `~${(m / 60).toFixed(1)} hr`;
}

const STATUS_STYLE: Record<string, string> = {
  draft: "bg-slate-100 text-slate-500",
  pending_consent: "bg-amber-100 text-amber-700",
  ready: "bg-green-100 text-green-700",
  revoked: "bg-red-100 text-red-700",
};

const STATUS_LABEL: Record<string, string> = {
  draft: "Draft — add media",
  pending_consent: "Awaiting consent",
  ready: "Ready",
  revoked: "Revoked",
};

function StatusBadge({ status }: { status: string }) {
  return (
    <span className={`rounded-full px-2 py-0.5 text-xs font-medium ${STATUS_STYLE[status] ?? ""}`}>
      {STATUS_LABEL[status] ?? status}
    </span>
  );
}

export default function PersonasPage() {
  const { user } = useAuth();
  const canEdit = user ? user.role !== "viewer" : false;
  const isAdmin = user?.role === "admin" || user?.role === "owner";

  const [personas, setPersonas] = useState<PersonaIdentity[]>([]);
  const [selected, setSelected] = useState<PersonaIdentity | null>(null);
  const [consents, setConsents] = useState<PersonaConsent[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [name, setName] = useState("");

  const load = useCallback(async () => {
    try {
      setPersonas(await personaApi.list());
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Failed to load personas");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { void load(); }, [load]);

  async function openDetail(id: string) {
    const p = await personaApi.get(id);
    setSelected(p);
    setConsents(await personaApi.listConsents(id));
  }

  async function refreshSelected() {
    if (!selected) return;
    const p = await personaApi.get(selected.id);
    setSelected(p);
    setConsents(await personaApi.listConsents(p.id));
    await load();
  }

  async function create(e: React.FormEvent) {
    e.preventDefault();
    if (!name.trim()) return;
    try {
      const p = await personaApi.create({ name });
      setName("");
      await load();
      setSelected(p);
      setConsents([]);
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Create failed");
    }
  }

  return (
    <>
      <PageHeader
        title="Avatar Personas"
        description="Consented digital-twin identities — likeness, voice, and the consent record that grounds them."
      />

      <div className="mb-4 rounded-lg border border-blue-200 bg-blue-50 px-3 py-2 text-xs text-blue-800">
        Every avatar/voice this platform ever generates is tied to one of these
        identities — and generation is only possible once its status is <strong>Ready</strong>,
        which requires both media (a training video or voice sample) <em>and</em> an
        active consent record from the real person being represented.
      </div>

      {error ? (
        <div className="mb-4 rounded-lg bg-red-50 px-3 py-2 text-sm text-red-700">{error}</div>
      ) : null}

      <div className="grid grid-cols-1 gap-4 lg:grid-cols-3">
        <div className="lg:col-span-1">
          {canEdit ? (
            <Card className="mb-4">
              <CardTitle>New persona</CardTitle>
              <form onSubmit={create} className="flex gap-2">
                <input
                  value={name} onChange={(e) => setName(e.target.value)}
                  placeholder="e.g. Jordan (Founder)"
                  className="grow rounded-lg border border-slate-300 px-3 py-2 text-sm"
                />
                <Button type="submit">Add</Button>
              </form>
            </Card>
          ) : null}

          <Card>
            <CardTitle>Personas</CardTitle>
            {loading ? (
              <Spinner />
            ) : personas.length === 0 ? (
              <p className="text-sm text-slate-400">None yet.</p>
            ) : (
              <ul className="divide-y divide-slate-100">
                {personas.map((p) => (
                  <li key={p.id}>
                    <button
                      onClick={() => void openDetail(p.id)}
                      className={`flex w-full items-center justify-between gap-2 py-2 text-left text-sm hover:bg-slate-50 ${
                        selected?.id === p.id ? "font-medium text-brand" : "text-slate-700"
                      }`}
                    >
                      <span>{p.name}</span>
                      <StatusBadge status={p.status} />
                    </button>
                  </li>
                ))}
              </ul>
            )}
          </Card>
        </div>

        <div className="lg:col-span-2">
          {selected ? (
            <PersonaDetail
              persona={selected}
              consents={consents}
              canEdit={canEdit}
              isAdmin={isAdmin}
              onChange={refreshSelected}
            />
          ) : (
            <Card><p className="text-sm text-slate-400">Select a persona to manage its media and consent.</p></Card>
          )}
        </div>
      </div>
    </>
  );
}

function UploadRow({
  label, accept, hasFile, onUpload, disabled,
}: {
  label: string; accept: string; hasFile: boolean;
  onUpload: (file: File) => Promise<void>; disabled: boolean;
}) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function handleChange(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0];
    if (!file) return;
    setBusy(true);
    setError(null);
    try {
      await onUpload(file);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Upload failed");
    } finally {
      setBusy(false);
      e.target.value = "";
    }
  }

  return (
    <div className="flex items-center justify-between gap-3 py-1.5">
      <span className="text-sm text-slate-700">
        {label} {hasFile ? <span className="text-green-600">✓ uploaded</span> : null}
      </span>
      <label className={`text-xs ${disabled ? "text-slate-300" : "cursor-pointer text-brand hover:underline"}`}>
        {busy ? "Uploading…" : hasFile ? "Replace" : "Upload"}
        <input type="file" accept={accept} className="hidden" disabled={disabled || busy} onChange={handleChange} />
      </label>
      {error ? <span className="text-xs text-red-600">{error}</span> : null}
    </div>
  );
}

function PersonaDetail({
  persona, consents, canEdit, isAdmin, onChange,
}: {
  persona: PersonaIdentity; consents: PersonaConsent[];
  canEdit: boolean; isAdmin: boolean; onChange: () => void;
}) {
  const [subjectName, setSubjectName] = useState("");
  const [subjectEmail, setSubjectEmail] = useState("");
  const [statement, setStatement] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const revoked = persona.status === "revoked";
  const activeConsent = consents.find((c) => c.is_active);

  async function grantConsent(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      await personaApi.grantConsent(persona.id, {
        subject_name: subjectName, subject_email: subjectEmail, consent_statement: statement,
      });
      setSubjectName(""); setSubjectEmail(""); setStatement("");
      onChange();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not record consent");
    } finally {
      setBusy(false);
    }
  }

  async function revoke() {
    if (!confirm(
      `Revoke consent for "${persona.name}"? This permanently blocks reuse — a new persona must be ` +
      `created if consent is granted again later.`,
    )) return;
    setBusy(true);
    try {
      await personaApi.revokeConsent(persona.id);
      onChange();
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="space-y-4">
      <Card>
        <div className="flex items-center justify-between">
          <CardTitle>{persona.name}</CardTitle>
          <StatusBadge status={persona.status} />
        </div>

        <div className="space-y-2 text-sm">
          <UploadRow
            label="Training video" accept="video/*" hasFile={!!persona.training_video_path}
            disabled={!canEdit || revoked}
            onUpload={(f) => personaApi.uploadTrainingVideo(persona.id, f).then(onChange)}
          />
          <UploadRow
            label="Voice sample" accept="audio/*" hasFile={!!persona.voice_sample_path}
            disabled={!canEdit || revoked}
            onUpload={(f) => personaApi.uploadVoiceSample(persona.id, f).then(onChange)}
          />
        </div>

        <div className="mt-3">
          <p className="mb-1 text-sm font-medium text-slate-700">Reference images</p>
          <div className="flex flex-wrap gap-2">
            {persona.reference_image_paths.map((path) => (
              <span key={path} className="flex items-center gap-1 rounded bg-slate-100 px-2 py-1 text-xs text-slate-600">
                {path.split("/").pop()}
                {canEdit && !revoked ? (
                  <button
                    onClick={() => personaApi.removeReferenceImage(persona.id, path).then(onChange)}
                    className="text-slate-400 hover:text-red-600"
                  >
                    ×
                  </button>
                ) : null}
              </span>
            ))}
          </div>
          {canEdit && !revoked ? (
            <label className="mt-2 inline-block cursor-pointer text-xs text-brand hover:underline">
              + Add reference image
              <input
                type="file" accept="image/*" className="hidden"
                onChange={(e) => {
                  const f = e.target.files?.[0];
                  if (f) void personaApi.uploadReferenceImage(persona.id, f).then(onChange);
                  e.target.value = "";
                }}
              />
            </label>
          ) : null}
        </div>
      </Card>

      <Card>
        <CardTitle>Consent</CardTitle>
        {revoked ? (
          <p className="text-sm text-red-600">
            Consent was revoked. This identity can no longer be used or edited.
          </p>
        ) : activeConsent ? (
          <div className="text-sm">
            <p className="text-green-700">
              ✓ Active consent from <strong>{activeConsent.subject_name}</strong> ({activeConsent.subject_email})
            </p>
            <p className="mt-1 text-xs text-slate-400">
              Granted {activeConsent.granted_at ? new Date(activeConsent.granted_at + "Z").toLocaleString() : "—"}
              {" · policy "}{activeConsent.policy_version}
            </p>
            <p className="mt-2 text-xs italic text-slate-500">&ldquo;{activeConsent.consent_statement}&rdquo;</p>
            {isAdmin ? (
              <Button variant="danger" className="mt-3" onClick={() => void revoke()} disabled={busy}>
                Revoke consent
              </Button>
            ) : null}
          </div>
        ) : isAdmin ? (
          <form onSubmit={grantConsent} className="space-y-2">
            <p className="mb-2 text-xs text-slate-400">
              Record the real person&apos;s attestation before this identity can be used for generation.
            </p>
            <input
              required value={subjectName} onChange={(e) => setSubjectName(e.target.value)}
              placeholder="Subject's full name"
              className="w-full rounded-lg border border-slate-300 px-3 py-2 text-sm"
            />
            <input
              required type="email" value={subjectEmail} onChange={(e) => setSubjectEmail(e.target.value)}
              placeholder="Subject's email"
              className="w-full rounded-lg border border-slate-300 px-3 py-2 text-sm"
            />
            <textarea
              required rows={3} value={statement} onChange={(e) => setStatement(e.target.value)}
              placeholder="I, [name], consent to RevOS creating an AI avatar of my likeness and voice for marketing use…"
              className="w-full rounded-lg border border-slate-300 px-3 py-2 text-sm"
            />
            {error ? <p className="text-xs text-red-600">{error}</p> : null}
            <Button type="submit" disabled={busy}>Record consent</Button>
          </form>
        ) : (
          <p className="text-sm text-slate-400">Only account admins can record consent.</p>
        )}
      </Card>

      {persona.status === "ready" && canEdit ? <GenerateVideoCard persona={persona} /> : null}
    </div>
  );
}

function GenerateVideoCard({ persona }: { persona: PersonaIdentity }) {
  const [durations, setDurations] = useState<AvatarDuration[]>([]);
  const [targetSeconds, setTargetSeconds] = useState(15);
  const [script, setScript] = useState("");
  const [jobs, setJobs] = useState<AvatarJob[]>([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const loadJobs = useCallback(async () => {
    try {
      setJobs(await avatarApi.listJobs(persona.id));
    } catch {
      /* non-fatal */
    }
  }, [persona.id]);

  useEffect(() => {
    avatarApi.durations().then((d) => setDurations(d.durations)).catch(() => setDurations([]));
    void loadJobs();
  }, [loadJobs]);

  // Poll while any job is still running.
  useEffect(() => {
    if (!jobs.some((j) => j.status === "queued" || j.status === "processing")) return;
    const t = setInterval(() => void loadJobs(), 15000);
    return () => clearInterval(t);
  }, [jobs, loadJobs]);

  const est = durations.find((d) => d.seconds === targetSeconds)?.estimated_seconds ?? null;

  async function generate(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      await avatarApi.createJob({
        persona_identity_id: persona.id, script, target_seconds: targetSeconds,
      });
      setScript("");
      await loadJobs();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not start generation");
    } finally {
      setBusy(false);
    }
  }

  return (
    <Card>
      <CardTitle>🎬 Generate avatar video</CardTitle>
      <div className="mb-3 rounded-lg border border-blue-200 bg-blue-50 px-3 py-2 text-xs text-blue-800">
        Generation runs entirely on your own server (no paid APIs) and is
        <strong> slow on CPU</strong> — see the estimate below. It runs in the background;
        you can leave this page and check back.
      </div>

      <form onSubmit={generate} className="space-y-2">
        <div className="flex items-center gap-2 text-sm">
          <label className="font-medium text-slate-700">Length</label>
          <select
            value={targetSeconds}
            onChange={(e) => setTargetSeconds(Number(e.target.value))}
            className="rounded-lg border border-slate-300 px-3 py-2"
          >
            {(durations.length ? durations.map((d) => d.seconds) : [7, 15, 30, 45, 60, 90, 120]).map((s) => (
              <option key={s} value={s}>{s}s</option>
            ))}
          </select>
          {est ? <span className="text-xs text-slate-500">est. wait {fmtWait(est)}</span> : null}
        </div>
        <textarea
          required rows={3} value={script} onChange={(e) => setScript(e.target.value)}
          placeholder="The script your avatar will speak…"
          className="w-full rounded-lg border border-slate-300 px-3 py-2 text-sm"
        />
        {error ? <p className="text-xs text-red-600">{error}</p> : null}
        <Button type="submit" disabled={busy || !script.trim()}>
          {busy ? "Starting…" : "Generate"}
        </Button>
      </form>

      {jobs.length ? (
        <ul className="mt-4 space-y-2">
          {jobs.map((j) => (
            <li key={j.id} className="rounded-lg border border-slate-200 p-2 text-sm">
              <div className="flex items-center justify-between">
                <span className="text-slate-600">
                  {j.target_seconds}s ·{" "}
                  <span className={
                    j.status === "succeeded" ? "text-green-600"
                      : j.status === "failed" ? "text-red-600"
                      : "text-amber-600"
                  }>
                    {j.status === "processing" ? "generating…"
                      : j.status === "queued" ? "queued"
                      : j.status}
                  </span>
                </span>
                {(j.status === "queued" || j.status === "processing") && j.estimated_seconds ? (
                  <span className="text-xs text-slate-400">est. {fmtWait(j.estimated_seconds)}</span>
                ) : null}
              </div>
              <p className="truncate text-xs text-slate-400">{j.script}</p>
              {j.status === "succeeded" && j.has_output ? (
                <video
                  src={avatarApi.videoUrl(j.id)}
                  controls
                  className="mt-2 max-h-64 w-full rounded"
                />
              ) : null}
              {j.status === "failed" && j.error ? (
                <p className="mt-1 text-xs text-red-600">{j.error}</p>
              ) : null}
            </li>
          ))}
        </ul>
      ) : null}
    </Card>
  );
}
