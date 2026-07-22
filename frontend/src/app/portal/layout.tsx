"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect } from "react";
import type { ReactNode } from "react";

import { Spinner } from "@/components/ui/Spinner";
import { AuthProvider, useAuth } from "@/lib/auth";

function Shell({ children }: { children: ReactNode }) {
  const { user, loading, logout } = useAuth();
  const router = useRouter();

  useEffect(() => {
    if (!loading && !user) router.replace("/login");
  }, [loading, user, router]);

  if (loading) {
    return (
      <div className="flex h-screen items-center justify-center bg-[#0b0713]">
        <Spinner label="Loading your portal…" />
      </div>
    );
  }
  if (!user) return null;

  return (
    <div className="min-h-screen bg-[#0b0713] text-white">
      <div
        className="pointer-events-none fixed inset-0 opacity-60"
        style={{
          background:
            "radial-gradient(60rem 40rem at 15% -10%, rgba(129,92,255,0.35), transparent 60%)," +
            "radial-gradient(50rem 35rem at 110% 10%, rgba(236,72,153,0.25), transparent 55%)," +
            "radial-gradient(40rem 30rem at 50% 120%, rgba(56,189,248,0.18), transparent 55%)",
        }}
      />
      <header className="relative z-10 flex items-center justify-between border-b border-white/10 px-5 py-4 sm:px-8">
        <Link href="/portal" className="flex items-center gap-2 font-semibold tracking-tight">
          <span className="inline-flex h-7 w-7 items-center justify-center rounded-lg bg-gradient-to-br from-violet-500 to-fuchsia-500 text-sm">
            ✦
          </span>
          <span>Creator Portal</span>
        </Link>
        <nav className="flex items-center gap-4 text-sm text-white/70">
          <Link href="/dashboard" className="hover:text-white">
            Business dashboard
          </Link>
          <button onClick={() => void logout()} className="hover:text-white">
            Sign out
          </button>
        </nav>
      </header>
      <main className="relative z-10 mx-auto max-w-5xl px-5 py-8 sm:px-8">{children}</main>
    </div>
  );
}

export default function PortalLayout({ children }: { children: ReactNode }) {
  return (
    <AuthProvider>
      <Shell>{children}</Shell>
    </AuthProvider>
  );
}
