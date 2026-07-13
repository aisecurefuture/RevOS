"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useState } from "react";

import { useAuth } from "@/lib/auth";
import { useBrand } from "@/lib/brand";
import {
  NAV_GROUPS,
  OVERVIEW_ITEM,
  UTILITY_ITEMS,
  type NavItem,
} from "@/lib/nav";
import type { Role } from "@/lib/types";

const ROLE_RANK: Record<Role, number> = {
  viewer: 0,
  editor: 1,
  admin: 2,
  owner: 3,
};

const COLLAPSE_KEY = "revos.navCollapsed"; // JSON: { [groupKey]: true } = collapsed

function loadCollapsed(): Record<string, boolean> {
  if (typeof window === "undefined") return {};
  try {
    return JSON.parse(window.localStorage.getItem(COLLAPSE_KEY) || "{}");
  } catch {
    return {};
  }
}

export function Sidebar({ open, onClose }: { open: boolean; onClose: () => void }) {
  const pathname = usePathname();
  const { user } = useAuth();
  const { brands, loading: brandsLoading } = useBrand();
  const rank = user ? ROLE_RANK[user.role] : 0;
  const [collapsed, setCollapsed] = useState<Record<string, boolean>>({});
  const [hydrated, setHydrated] = useState(false);

  useEffect(() => {
    setCollapsed(loadCollapsed());
    setHydrated(true);
  }, []);

  // Close the mobile drawer automatically on navigation.
  useEffect(() => {
    onClose();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [pathname]);

  function toggleGroup(key: string) {
    setCollapsed((prev) => {
      const next = { ...prev, [key]: !prev[key] };
      try {
        window.localStorage.setItem(COLLAPSE_KEY, JSON.stringify(next));
      } catch {
        /* private mode — collapse state just won't persist */
      }
      return next;
    });
  }

  // Zero-brands accounts get Define forced open — it's where onboarding points.
  const forceDefineOpen = !brandsLoading && brands.length === 0;

  const visible = (item: NavItem) => !item.minRole || rank >= ROLE_RANK[item.minRole];

  const isActive = (href: string) =>
    href === "/dashboard" ? pathname === "/dashboard" : pathname.startsWith(href);

  const itemLink = (item: NavItem) => (
    <Link
      key={item.href}
      href={item.href}
      className={`flex items-center gap-3 rounded-lg px-3 py-2 text-sm font-medium transition-colors ${
        isActive(item.href) ? "bg-brand/10 text-brand" : "text-slate-600 hover:bg-slate-100"
      }`}
    >
      <span aria-hidden>{item.icon}</span>
      {item.label}
    </Link>
  );

  return (
    <>
      {open ? (
        <div
          className="fixed inset-0 z-40 bg-black/30 md:hidden"
          onClick={onClose}
          aria-hidden="true"
        />
      ) : null}
      <aside
        className={`fixed inset-y-0 left-0 z-50 flex w-60 shrink-0 -translate-x-full flex-col border-r border-slate-200 bg-white transition-transform duration-200 md:static md:z-auto md:translate-x-0 ${
          open ? "translate-x-0" : ""
        }`}
      >
        <div className="flex h-16 items-center justify-between border-b border-slate-200 px-5">
          <img src="/logo.svg" alt="RevOS360" width={130} height={29} />
          <button
            type="button"
            onClick={onClose}
            aria-label="Close menu"
            className="rounded-lg p-1 text-slate-400 hover:bg-slate-100 md:hidden"
          >
            ✕
          </button>
        </div>

        <nav className="flex-1 space-y-1 overflow-y-auto p-3">
          {itemLink(OVERVIEW_ITEM)}

          {NAV_GROUPS.map((group) => {
            const items = group.items.filter(visible);
            if (items.length === 0) return null;
            const isCollapsed =
              hydrated && !(group.key === "define" && forceDefineOpen) && !!collapsed[group.key];
            return (
              <div key={group.key} className="pt-2">
                <button
                  type="button"
                  onClick={() => toggleGroup(group.key)}
                  aria-expanded={!isCollapsed}
                  className="flex w-full items-center justify-between rounded-lg px-3 py-1.5 text-xs font-semibold uppercase tracking-wider text-slate-400 hover:bg-slate-50 hover:text-slate-600"
                >
                  {group.label}
                  <span aria-hidden className={`transition-transform ${isCollapsed ? "" : "rotate-90"}`}>
                    ›
                  </span>
                </button>
                {!isCollapsed ? (
                  <div className="mt-0.5 space-y-0.5">
                    {items.map((item) => (
                      <div key={item.href}>
                        {item.subGroup ? (
                          <div className="mt-2 px-3 pb-0.5 text-[10px] font-semibold uppercase tracking-widest text-slate-300">
                            {item.subGroup}
                          </div>
                        ) : null}
                        {itemLink(item)}
                      </div>
                    ))}
                  </div>
                ) : null}
              </div>
            );
          })}
        </nav>

        <div className="space-y-0.5 border-t border-slate-200 p-3">
          {UTILITY_ITEMS.filter(visible).map(itemLink)}
          <div className="px-3 pt-2 text-xs text-slate-400">
            <p className="mb-1">Approval-first automation</p>
            <div className="flex gap-3">
              <Link href="/privacy" className="hover:text-slate-600 hover:underline">Privacy</Link>
              <Link href="/terms" className="hover:text-slate-600 hover:underline">Terms</Link>
            </div>
          </div>
        </div>
      </aside>
    </>
  );
}

