"use client";

import { useAuth } from "@/lib/auth";

import { BrandSelector } from "./BrandSelector";
import { Button } from "./ui/Button";

export function Topbar({ onMenuClick }: { onMenuClick: () => void }) {
  const { user, logout } = useAuth();

  return (
    <header className="flex h-16 shrink-0 items-center justify-between gap-2 border-b border-slate-200 bg-white px-4 sm:px-6">
      <div className="flex min-w-0 items-center gap-3">
        <button
          type="button"
          onClick={onMenuClick}
          aria-label="Open menu"
          className="-ml-1 rounded-lg p-2 text-slate-500 hover:bg-slate-100 md:hidden"
        >
          ☰
        </button>
        <BrandSelector />
      </div>
      <div className="flex shrink-0 items-center gap-2 sm:gap-4">
        {user ? (
          <div className="hidden text-right sm:block">
            <p className="text-sm font-medium text-slate-800">{user.full_name || user.email}</p>
            <p className="text-xs capitalize text-slate-400">{user.role}</p>
          </div>
        ) : null}
        <Button variant="secondary" onClick={() => void logout()} className="shrink-0">
          Sign out
        </Button>
      </div>
    </header>
  );
}
