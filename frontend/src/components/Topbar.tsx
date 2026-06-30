"use client";

import { useAuth } from "@/lib/auth";

import { BrandSelector } from "./BrandSelector";
import { Button } from "./ui/Button";

export function Topbar() {
  const { user, logout } = useAuth();

  return (
    <header className="flex h-16 shrink-0 items-center justify-between border-b border-slate-200 bg-white px-6">
      <BrandSelector />
      <div className="flex items-center gap-4">
        {user ? (
          <div className="text-right">
            <p className="text-sm font-medium text-slate-800">{user.full_name || user.email}</p>
            <p className="text-xs capitalize text-slate-400">{user.role}</p>
          </div>
        ) : null}
        <Button variant="secondary" onClick={() => void logout()}>
          Sign out
        </Button>
      </div>
    </header>
  );
}
