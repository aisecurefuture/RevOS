"use client";

import { useCallback, useEffect, useState } from "react";

import { PageHeader } from "@/components/PageHeader";
import { Button } from "@/components/ui/Button";
import { Card, CardTitle } from "@/components/ui/Card";
import { Spinner } from "@/components/ui/Spinner";
import {
  accountsApi,
  ApiError,
  type InvitationOut,
  type MemberOut,
  type MembershipOut,
} from "@/lib/api";
import { useAuth } from "@/lib/auth";

const ROLES = ["viewer", "editor", "admin", "owner"];
const ta = "rounded-lg border border-slate-300 px-3 py-2 text-sm";

export default function TeamPage() {
  const { user } = useAuth();

  const [memberships, setMemberships] = useState<MembershipOut[]>([]);
  const [members, setMembers] = useState<MemberOut[]>([]);
  const [invitations, setInvitations] = useState<InvitationOut[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const active = memberships.find((m) => m.is_active);
  const accountId = active?.account.id ?? null;
  const myRole = active?.role ?? null;
  const isAdmin = myRole === "admin" || myRole === "owner";
  const isOwner = myRole === "owner";

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const memberships = await accountsApi.list();
      setMemberships(memberships);
      const acct = memberships.find((m) => m.is_active);
      if (acct) {
        const [m, i] = await Promise.all([
          accountsApi.listMembers(acct.account.id),
          accountsApi.listInvitations(acct.account.id).catch(() => [] as InvitationOut[]),
        ]);
        setMembers(m);
        setInvitations(i);
      }
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Failed to load team");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  if (loading) {
    return (
      <>
        <PageHeader title="Team" description="Who has access to this workspace." />
        <Spinner />
      </>
    );
  }

  return (
    <>
      <PageHeader title="Team" description="Who has access to this workspace." />
      {error ? <div className="mb-4 rounded-lg bg-red-50 px-3 py-2 text-sm text-red-700">{error}</div> : null}

      {accountId ? (
        <div className="space-y-4">
          <MembersCard
            accountId={accountId}
            members={members}
            myUserId={user?.id ?? null}
            isOwner={isOwner}
            isAdmin={isAdmin}
            onChange={load}
          />
          {isAdmin ? (
            <InviteCard accountId={accountId} onSent={load} />
          ) : null}
          {isAdmin ? (
            <InvitationsCard accountId={accountId} invitations={invitations} onChange={load} />
          ) : null}
        </div>
      ) : (
        <Card><p className="text-sm text-slate-400">No active workspace.</p></Card>
      )}
    </>
  );
}

function MembersCard({
  accountId, members, myUserId, isOwner, isAdmin, onChange,
}: {
  accountId: string; members: MemberOut[]; myUserId: string | null;
  isOwner: boolean; isAdmin: boolean; onChange: () => void;
}) {
  const [busyId, setBusyId] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [resetFor, setResetFor] = useState<string | null>(null);
  const [resetResult, setResetResult] = useState<{ email: string; temp: string | null; emailed: boolean } | null>(null);

  async function resetPassword(userId: string, mode: "link" | "temp") {
    setBusyId(userId);
    setError(null);
    setResetResult(null);
    try {
      const r = await accountsApi.resetMemberPassword(accountId, userId, mode);
      setResetResult({ email: r.email, temp: r.temporary_password, emailed: r.emailed });
      setResetFor(null);
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Could not reset password");
    } finally {
      setBusyId(null);
    }
  }

  async function setRole(userId: string, role: string) {
    setBusyId(userId);
    setError(null);
    try {
      await accountsApi.changeMemberRole(accountId, userId, role);
      onChange();
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Could not update role");
    } finally {
      setBusyId(null);
    }
  }

  async function remove(userId: string) {
    if (!confirm("Remove this member from the workspace?")) return;
    setBusyId(userId);
    setError(null);
    try {
      await accountsApi.removeMember(accountId, userId);
      onChange();
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Could not remove member");
    } finally {
      setBusyId(null);
    }
  }

  return (
    <Card>
      <CardTitle>Members</CardTitle>
      {error ? <p className="mb-2 text-xs text-red-600">{error}</p> : null}
      {resetResult ? (
        <div className="mb-3 rounded-lg border border-green-200 bg-green-50 px-3 py-2 text-sm text-green-800">
          {resetResult.temp ? (
            <>
              <p className="font-medium">Temporary password for {resetResult.email}:</p>
              <div className="mt-1 flex items-center gap-2">
                <code className="rounded bg-white px-2 py-1 font-mono text-slate-800">{resetResult.temp}</code>
                <button
                  className="text-xs text-brand hover:underline"
                  onClick={() => void navigator.clipboard?.writeText(resetResult.temp!)}
                >
                  Copy
                </button>
              </div>
              <p className="mt-1 text-xs text-green-700">
                Share this securely — it&apos;s shown once. Their existing sessions were signed out.
              </p>
            </>
          ) : (
            <p>
              {resetResult.emailed
                ? `A password-reset link was emailed to ${resetResult.email}.`
                : `Reset requested for ${resetResult.email}, but email delivery isn't configured — use "Set temporary password" instead.`}
            </p>
          )}
          <button className="mt-1 text-xs text-slate-400 hover:text-slate-600" onClick={() => setResetResult(null)}>
            Dismiss
          </button>
        </div>
      ) : null}
      <ul className="divide-y divide-slate-100">
        {members.map((m) => {
          const isSelf = m.user_id === myUserId;
          const canManage = isOwner && m.role !== "owner" && !isSelf;
          // Admins can reset editors/viewers; only owners can reset an admin/owner.
          const canReset =
            isAdmin && !isSelf && (isOwner || (m.role !== "owner" && m.role !== "admin"));
          return (
            <li key={m.user_id} className="py-2 text-sm">
              <div className="flex items-center justify-between gap-3">
                <div>
                  <span className="font-medium text-slate-700">{m.full_name || m.email}</span>
                  <span className="ml-2 text-xs text-slate-400">{m.email}</span>
                  {isSelf ? <span className="ml-2 text-xs text-slate-400">(you)</span> : null}
                </div>
                <div className="flex items-center gap-2">
                  {canManage ? (
                    <select
                      className={ta} value={m.role} disabled={busyId === m.user_id}
                      onChange={(e) => void setRole(m.user_id, e.target.value)}
                    >
                      {ROLES.map((r) => <option key={r} value={r}>{r}</option>)}
                    </select>
                  ) : (
                    <span className="rounded-full bg-slate-100 px-2 py-0.5 text-xs text-slate-500">{m.role}</span>
                  )}
                  {canReset ? (
                    <button
                      className="text-xs text-slate-500 hover:text-brand"
                      disabled={busyId === m.user_id}
                      onClick={() => setResetFor(resetFor === m.user_id ? null : m.user_id)}
                    >
                      Reset password
                    </button>
                  ) : null}
                  {canManage ? (
                    <button
                      className="text-xs text-slate-400 hover:text-red-600"
                      disabled={busyId === m.user_id}
                      onClick={() => void remove(m.user_id)}
                    >
                      Remove
                    </button>
                  ) : null}
                </div>
              </div>
              {resetFor === m.user_id ? (
                <div className="mt-2 flex flex-wrap items-center gap-2 rounded-lg bg-slate-50 px-3 py-2">
                  <span className="text-xs text-slate-500">Reset {m.email} —</span>
                  <button
                    className="rounded-lg border border-slate-300 bg-white px-3 py-1 text-xs font-medium hover:bg-slate-50"
                    disabled={busyId === m.user_id}
                    onClick={() => void resetPassword(m.user_id, "link")}
                  >
                    Email reset link
                  </button>
                  <button
                    className="rounded-lg border border-slate-300 bg-white px-3 py-1 text-xs font-medium hover:bg-slate-50"
                    disabled={busyId === m.user_id}
                    onClick={() => void resetPassword(m.user_id, "temp")}
                  >
                    Set temporary password
                  </button>
                </div>
              ) : null}
            </li>
          );
        })}
      </ul>
    </Card>
  );
}

function InviteCard({ accountId, onSent }: { accountId: string; onSent: () => void }) {
  const [email, setEmail] = useState("");
  const [role, setRole] = useState("editor");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [acceptUrl, setAcceptUrl] = useState<string | null>(null);

  async function invite(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    setAcceptUrl(null);
    try {
      const invite = await accountsApi.inviteMember(accountId, email, role);
      setEmail("");
      setAcceptUrl(invite.accept_url);
      onSent();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not send invitation");
    } finally {
      setBusy(false);
    }
  }

  return (
    <Card>
      <CardTitle>Invite someone</CardTitle>
      <form onSubmit={invite} className="flex flex-wrap items-center gap-2">
        <input
          type="email" required value={email} onChange={(e) => setEmail(e.target.value)}
          placeholder="teammate@example.com" className={`${ta} grow`}
        />
        <select className={ta} value={role} onChange={(e) => setRole(e.target.value)}>
          {ROLES.filter((r) => r !== "owner").map((r) => <option key={r} value={r}>{r}</option>)}
        </select>
        <Button type="submit" disabled={busy}>{busy ? "Sending…" : "Send invite"}</Button>
      </form>
      {error ? <p className="mt-2 text-xs text-red-600">{error}</p> : null}
      {acceptUrl ? (
        <p className="mt-2 text-xs text-green-600">
          Invitation sent. Accept link (also emailed): <code className="text-slate-500">{acceptUrl}</code>
        </p>
      ) : null}
    </Card>
  );
}

function InvitationsCard({
  accountId, invitations, onChange,
}: { accountId: string; invitations: InvitationOut[]; onChange: () => void }) {
  const [busyId, setBusyId] = useState<string | null>(null);

  async function revoke(id: string) {
    setBusyId(id);
    try {
      await accountsApi.revokeInvitation(accountId, id);
      onChange();
    } finally {
      setBusyId(null);
    }
  }

  if (invitations.length === 0) return null;

  return (
    <Card>
      <CardTitle>Pending invitations</CardTitle>
      <ul className="divide-y divide-slate-100">
        {invitations.map((i) => (
          <li key={i.id} className="flex items-center justify-between py-2 text-sm">
            <div>
              <span className="text-slate-700">{i.email}</span>
              <span className="ml-2 rounded-full bg-slate-100 px-2 py-0.5 text-xs text-slate-500">{i.role}</span>
            </div>
            <button
              className="text-xs text-slate-400 hover:text-red-600"
              disabled={busyId === i.id}
              onClick={() => void revoke(i.id)}
            >
              Revoke
            </button>
          </li>
        ))}
      </ul>
    </Card>
  );
}
