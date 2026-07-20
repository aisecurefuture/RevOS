"use client";

// Platform super-admin console. Access is gated server-side by the
// PLATFORM_ADMIN_EMAILS allowlist (every endpoint requires it); this page
// additionally hides itself for non-admins as a UX nicety.

import { useCallback, useEffect, useState } from "react";

import { PageHeader } from "@/components/PageHeader";
import { Button } from "@/components/ui/Button";
import { Card, CardTitle } from "@/components/ui/Card";
import { Spinner } from "@/components/ui/Spinner";
import { ApiError, platformAdminApi, type AdminAccount, type AdminUser } from "@/lib/api";
import { useAuth } from "@/lib/auth";

const inp = "rounded-lg border border-slate-300 px-3 py-2 text-sm";

export default function AdminPage() {
  const { user } = useAuth();
  const [accounts, setAccounts] = useState<AdminAccount[]>([]);
  const [users, setUsers] = useState<AdminUser[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const [a, u] = await Promise.all([platformAdminApi.listAccounts(), platformAdminApi.listUsers()]);
      setAccounts(a);
      setUsers(u);
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Failed to load admin data");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { void load(); }, [load]);

  if (user && !user.is_platform_admin) {
    return (
      <>
        <PageHeader title="Admin" description="Platform administration." />
        <Card><p className="text-sm text-slate-500">You don&apos;t have platform-admin access.</p></Card>
      </>
    );
  }

  async function run(fn: () => Promise<unknown>, msg: string) {
    setError(null);
    setNotice(null);
    try {
      await fn();
      setNotice(msg);
      await load();
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Action failed");
    }
  }

  return (
    <>
      <PageHeader title="Platform Admin" description="Manage tenants and users across the platform." />
      {error ? <div className="mb-4 rounded-lg bg-red-50 px-3 py-2 text-sm text-red-700">{error}</div> : null}
      {notice ? <div className="mb-4 rounded-lg bg-green-50 px-3 py-2 text-sm text-green-700">{notice}</div> : null}

      {loading ? <Spinner /> : (
        <div className="space-y-4">
          <CreateTenantCard onCreated={(m) => { setNotice(m); void load(); }} />

          <Card>
            <CardTitle>Tenants ({accounts.length})</CardTitle>
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="text-left text-xs uppercase tracking-wide text-slate-400">
                    <th className="py-2">Name</th><th>Owner</th><th>Members</th><th>Plan</th><th>Status</th><th></th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-100">
                  {accounts.map((a) => (
                    <tr key={a.id}>
                      <td className="py-2 font-medium text-slate-700">{a.name}<span className="ml-2 text-xs text-slate-400">{a.type}</span></td>
                      <td className="text-slate-500">{a.owner_email ?? "—"}</td>
                      <td className="text-slate-500">{a.member_count}</td>
                      <td>
                        {a.plan === "comp" ? (
                          <span className="rounded-full bg-purple-100 px-2 py-0.5 text-xs text-purple-700">Comp</span>
                        ) : (
                          <span className="text-xs text-slate-500">
                            {a.plan ?? "—"}{a.billing_status && a.plan ? ` · ${a.billing_status}` : ""}
                          </span>
                        )}
                      </td>
                      <td>
                        {a.disabled ? (
                          <span className="rounded-full bg-red-100 px-2 py-0.5 text-xs text-red-700">Disabled</span>
                        ) : (
                          <span className="rounded-full bg-green-100 px-2 py-0.5 text-xs text-green-700">Active</span>
                        )}
                      </td>
                      <td className="text-right">
                        <span className="inline-flex items-center gap-3">
                          {a.plan === "comp" && a.billing_status === "active" ? (
                            <button className="text-xs text-amber-600 hover:underline"
                              onClick={() => {
                                if (confirm(`Revoke complimentary access for "${a.name}"? They'll hit the paywall unless they subscribe.`))
                                  void run(() => platformAdminApi.setAccountComp(a.id, false), "Comp access revoked");
                              }}>
                              Revoke comp
                            </button>
                          ) : (
                            <button className="text-xs text-purple-600 hover:underline"
                              onClick={() => {
                                if (confirm(`Grant "${a.name}" complimentary access? They bypass the trial/paywall entirely.`))
                                  void run(() => platformAdminApi.setAccountComp(a.id, true), "Comp access granted");
                              }}>
                              Grant comp
                            </button>
                          )}
                          {a.disabled ? (
                            <button className="text-xs text-brand hover:underline"
                              onClick={() => run(() => platformAdminApi.enableAccount(a.id), "Tenant enabled")}>
                              Enable
                            </button>
                          ) : (
                            <button className="text-xs text-red-500 hover:underline"
                              onClick={() => {
                                const reason = prompt(`Disable "${a.name}"? Optional reason:`) ?? undefined;
                                if (reason !== null) void run(() => platformAdminApi.disableAccount(a.id, reason), "Tenant disabled");
                              }}>
                              Disable
                            </button>
                          )}
                        </span>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </Card>

          <Card>
            <CardTitle>Users ({users.length})</CardTitle>
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="text-left text-xs uppercase tracking-wide text-slate-400">
                    <th className="py-2">Email</th><th>Name</th><th>Status</th><th></th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-100">
                  {users.map((u) => (
                    <tr key={u.id}>
                      <td className="py-2 text-slate-700">{u.email}</td>
                      <td className="text-slate-500">{u.full_name || "—"}</td>
                      <td className="space-x-1">
                        {!u.is_active ? <span className="rounded-full bg-red-100 px-2 py-0.5 text-xs text-red-700">Disabled</span> : null}
                        {u.locked ? <span className="rounded-full bg-amber-100 px-2 py-0.5 text-xs text-amber-700">Locked</span> : null}
                        {u.is_active && !u.locked ? <span className="rounded-full bg-green-100 px-2 py-0.5 text-xs text-green-700">Active</span> : null}
                      </td>
                      <td className="space-x-3 text-right">
                        {u.locked ? (
                          <button className="text-xs text-brand hover:underline"
                            onClick={() => run(() => platformAdminApi.unlockUser(u.id), "User unlocked")}>
                            Unlock
                          </button>
                        ) : null}
                        {u.is_active ? (
                          <button className="text-xs text-red-500 hover:underline"
                            onClick={() => run(() => platformAdminApi.disableUser(u.id), "User disabled")}>
                            Disable
                          </button>
                        ) : (
                          <button className="text-xs text-brand hover:underline"
                            onClick={() => run(() => platformAdminApi.enableUser(u.id), "User enabled")}>
                            Enable
                          </button>
                        )}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </Card>
        </div>
      )}
    </>
  );
}

function CreateTenantCard({ onCreated }: { onCreated: (msg: string) => void }) {
  const [name, setName] = useState("");
  const [lead, setLead] = useState("");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setErr(null);
    try {
      const r = await platformAdminApi.createTenant(name, lead);
      setName(""); setLead("");
      onCreated(
        r.invited
          ? `Created "${r.name}" and invited ${r.lead_email} as the team lead.`
          : `Created "${r.name}" owned by ${r.lead_email}.`,
      );
    } catch (e) {
      setErr(e instanceof ApiError ? e.message : "Could not create tenant");
    } finally {
      setBusy(false);
    }
  }

  return (
    <Card>
      <CardTitle>Create tenant</CardTitle>
      <form onSubmit={submit} className="flex flex-wrap items-end gap-2">
        <div>
          <label className="mb-1 block text-xs font-medium text-slate-500">Workspace name</label>
          <input required className={inp} value={name} onChange={(e) => setName(e.target.value)} placeholder="Acme Corp" />
        </div>
        <div className="grow">
          <label className="mb-1 block text-xs font-medium text-slate-500">Team lead email</label>
          <input required type="email" className={`${inp} w-full`} value={lead} onChange={(e) => setLead(e.target.value)} placeholder="lead@acme.com" />
        </div>
        <Button type="submit" disabled={busy}>{busy ? "Creating…" : "Create + email lead"}</Button>
        {err ? <p className="w-full text-xs text-red-600">{err}</p> : null}
      </form>
      <p className="mt-2 text-xs text-slate-400">
        If the lead already has an account they become owner; otherwise the workspace is created and
        they&apos;re emailed an invite as admin.
      </p>
    </Card>
  );
}
