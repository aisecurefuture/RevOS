"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

import { useAuth } from "@/lib/auth";
import { NAV_ITEMS } from "@/lib/nav";
import type { Role } from "@/lib/types";

const ROLE_RANK: Record<Role, number> = {
  viewer: 0,
  editor: 1,
  admin: 2,
  owner: 3,
};

export function Sidebar() {
  const pathname = usePathname();
  const { user } = useAuth();
  const rank = user ? ROLE_RANK[user.role] : 0;

  const items = NAV_ITEMS.filter(
    (i) => !i.minRole || rank >= ROLE_RANK[i.minRole],
  );

  return (
    <aside className="flex w-60 shrink-0 flex-col border-r border-slate-200 bg-white">
      <div className="flex h-16 items-center border-b border-slate-200 px-5">
        <img src="/logo.svg" alt="RevOS360" width={130} height={29} />
      </div>
      <nav className="flex-1 space-y-1 overflow-y-auto p-3">
        {items.map((item) => {
          const active =
            item.href === "/dashboard"
              ? pathname === "/dashboard"
              : pathname.startsWith(item.href);
          return (
            <Link
              key={item.href}
              href={item.href}
              className={`flex items-center gap-3 rounded-lg px-3 py-2 text-sm font-medium transition-colors ${
                active
                  ? "bg-brand/10 text-brand"
                  : "text-slate-600 hover:bg-slate-100"
              }`}
            >
              <span aria-hidden>{item.icon}</span>
              {item.label}
            </Link>
          );
        })}
      </nav>
      <div className="border-t border-slate-200 p-4 text-xs text-slate-400">
        <p className="mb-1">Approval-first automation</p>
        <div className="flex gap-3">
          <Link href="/privacy" className="hover:text-slate-600 hover:underline">Privacy</Link>
          <Link href="/terms" className="hover:text-slate-600 hover:underline">Terms</Link>
        </div>
      </div>
    </aside>
  );
}
