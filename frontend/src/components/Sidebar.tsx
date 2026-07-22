"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useState } from "react";

import { usePendingApprovals } from "@/lib/approvals";
import { useAuth } from "@/lib/auth";
import { useBrand } from "@/lib/brand";
import {
  APPROVALS_ITEM,
  NAV_GROUPS,
  OVERVIEW_ITEM,
  PLATFORM_ADMIN_ITEM,
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
      data-tour={item.href === "/dashboard/brand-book" ? "brand-book" : undefined}
      className={`flex items-center gap-3 rounded-lg px-3 py-2 text-sm font-medium transition-colors ${
        isActive(item.href)
          ? "bg-gradient-to-r from-violet-500/20 to-fuchsia-500/10 text-white"
          : "text-white/55 hover:bg-white/[0.06] hover:text-white"
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
        className={`fixed inset-y-0 left-0 z-50 flex w-60 shrink-0 -translate-x-full flex-col border-r border-white/10 bg-white/[0.02] backdrop-blur-xl transition-transform duration-200 md:static md:z-auto md:translate-x-0 ${
          open ? "translate-x-0" : ""
        }`}
      >
        <div className="flex h-16 items-center justify-between border-b border-white/10 px-5">
          <span className="flex items-center gap-2 font-semibold tracking-tight text-white">
            <span className="inline-flex h-7 w-7 items-center justify-center rounded-lg bg-gradient-to-br from-violet-500 to-fuchsia-500 text-xs">
              ✦
            </span>
            RevOS<span className="text-violet-400">360</span>
          </span>
          <button
            type="button"
            onClick={onClose}
            aria-label="Close menu"
            className="rounded-lg p-1 text-white/40 hover:bg-white/[0.06] md:hidden"
          >
            ✕
          </button>
        </div>

        <nav data-tour="nav" className="flex-1 space-y-1 overflow-y-auto p-3">
          {itemLink(OVERVIEW_ITEM)}
          <ApprovalsPin active={isActive(APPROVALS_ITEM.href)} />

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
                  className="flex w-full items-center justify-between rounded-lg px-3 py-1.5 text-xs font-semibold uppercase tracking-wider text-white/30 hover:bg-white/[0.04] hover:text-white/60"
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
                          <div className="mt-2 px-3 pb-0.5 text-[10px] font-semibold uppercase tracking-widest text-white/25">
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

        <div className="space-y-0.5 border-t border-white/10 p-3">
          {user?.is_platform_admin ? itemLink(PLATFORM_ADMIN_ITEM) : null}
          {UTILITY_ITEMS.filter(visible).map(itemLink)}
          <div className="px-3 pt-2 text-xs text-white/25">
            <p className="mb-1">Approval-first automation</p>
            <div className="flex gap-3">
              <Link href="/privacy" className="hover:text-white/60 hover:underline">Privacy</Link>
              <Link href="/terms" className="hover:text-white/60 hover:underline">Terms</Link>
            </div>
          </div>
        </div>
      </aside>
    </>
  );
}


// The wedge: Approvals pinned directly under Overview with its own visual
// weight — accent-bordered, badge-carrying. Deliberately NOT alert styling
// (brand accent, not red); this reads "the important surface", not
// "something is wrong". Approvals also stays listed in Govern — same route,
// two entry points, one mental model.
function ApprovalsPin({ active }: { active: boolean }) {
  const { pendingCount } = usePendingApprovals();
  return (
    <Link
      href={APPROVALS_ITEM.href}
      data-tour="approvals"
      className={`flex items-center justify-between rounded-lg border px-3 py-2 text-sm font-semibold transition-colors ${
        active
          ? "border-violet-400/50 bg-gradient-to-r from-violet-500/20 to-fuchsia-500/10 text-white"
          : "border-violet-400/25 bg-violet-500/[0.06] text-white/70 hover:border-violet-400/50 hover:bg-violet-500/10 hover:text-white"
      }`}
    >
      <span className="flex items-center gap-3">
        <span aria-hidden>{APPROVALS_ITEM.icon}</span>
        {APPROVALS_ITEM.label}
      </span>
      {pendingCount > 0 ? (
        <span className="rounded-full bg-gradient-to-br from-violet-500 to-fuchsia-500 px-2 py-0.5 text-xs font-bold text-white">
          {pendingCount > 99 ? "99+" : pendingCount}
        </span>
      ) : null}
    </Link>
  );
}
