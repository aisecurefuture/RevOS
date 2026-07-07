"use client";

import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { Suspense, useEffect, useState } from "react";

import { accountsApi, ApiError, authApi } from "@/lib/api";
import { useAuth } from "@/lib/auth";

function Shell({ children }: { children: React.ReactNode }) {
  return (
    <div className="flex min-h-screen items-center justify-center bg-slate-50 px-4">
      <div className="w-full max-w-sm rounded-2xl border border-slate-200 bg-white p-8 text-center shadow-sm">
        <img src="/logo.svg" alt="RevOS360" width={160} height={36} className="mx-auto mb-6" />
        {children}
      </div>
    </div>
  );
}

function JoinForm() {
  const router = useRouter();
  const params = useSearchParams();
  const token = params.get("token") || "";
  const { user, loading, refreshUser } = useAuth();

  const [status, setStatus] = useState<"waiting" | "accepting" | "error">("waiting");
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (loading || !token || !user || status !== "waiting") return;
    setStatus("accepting");
    (async () => {
      try {
        const { account_id } = await authApi.acceptInvitation(token);
        await accountsApi.switchAccount(account_id);
        // The auth cookie now carries the new account/role — refresh the
        // cached user before landing on the dashboard so role-gated UI (and
        // this new active account) reflects it immediately.
        await refreshUser();
        router.replace("/dashboard");
      } catch (err) {
        setStatus("error");
        setError(err instanceof ApiError ? err.message : "Could not accept this invitation.");
      }
    })();
  }, [loading, user, token, status, router, refreshUser]);

  if (!token) {
    return <p className="text-sm text-slate-500">This invitation link is missing its token.</p>;
  }

  if (loading || status === "accepting") {
    return <p className="text-sm text-slate-500">Joining the workspace…</p>;
  }

  if (status === "error") {
    return (
      <>
        <p className="text-sm text-red-600">{error}</p>
        <p className="mt-3 text-xs text-slate-400">
          If you already have a RevOS account, make sure you&apos;re signed in with the email
          address the invitation was sent to.
        </p>
      </>
    );
  }

  if (!user) {
    const next = `/join?token=${encodeURIComponent(token)}`;
    return (
      <>
        <p className="mb-4 text-sm text-slate-600">
          Sign in or create an account with the invited email address to accept this invitation.
        </p>
        <div className="space-y-2">
          <Link
            href={`/login?next=${encodeURIComponent(next)}`}
            className="block w-full rounded-lg bg-brand px-4 py-2 text-sm font-medium text-white hover:opacity-90"
          >
            Log in
          </Link>
          <Link
            href={`/register?next=${encodeURIComponent(next)}`}
            className="block w-full rounded-lg border border-slate-300 px-4 py-2 text-sm font-medium text-slate-700 hover:bg-slate-50"
          >
            Create an account
          </Link>
        </div>
      </>
    );
  }

  return <p className="text-sm text-slate-500">Joining the workspace…</p>;
}

export default function JoinPage() {
  return (
    <Shell>
      <Suspense fallback={<p className="text-sm text-slate-500">Loading…</p>}>
        <JoinForm />
      </Suspense>
    </Shell>
  );
}
