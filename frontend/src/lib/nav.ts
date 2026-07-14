// Sidebar navigation config — three mental-model tiers reflecting the product
// thesis: DEFINE the source of truth (brand), REACH people as expressions of
// it, GOVERN what goes out (approval-first is the wedge).
//
// Tier + sub-group labels are plain exported constants (no i18n layer in this
// app) so renaming after user testing is a one-line change, not a refactor.

import type { Role } from "./types";

export interface NavItem {
  label: string;
  href: string;
  icon: string; // simple emoji glyphs keep the shell dependency-free
  minRole?: Role;
  /** Optional sub-group label rendered as a subtle divider above this item. */
  subGroup?: string;
}

export interface NavGroup {
  key: string;
  label: string;
  items: NavItem[];
}

// --- Swappable labels (candidates for A/B once there's traffic) --------------
export const TIER_DEFINE = "Define";
export const TIER_REACH = "Reach";
export const TIER_GOVERN = "Govern";
export const SUB_CAPTURE = "Capture";
export const SUB_COMMUNICATE = "Communicate";
export const SUB_PUBLISH = "Publish";

/** Pinned above the groups — the landing surface. */
export const OVERVIEW_ITEM: NavItem = { label: "Overview", href: "/dashboard", icon: "📊" };

/** The wedge: pinned, visually distinct, carries the pending-count badge. */
export const APPROVALS_ITEM: NavItem = { label: "Approvals", href: "/dashboard/approvals", icon: "✅" };

/** Platform super-admin console — shown only to PLATFORM_ADMIN_EMAILS users
 * (gated by is_platform_admin, not a role). */
export const PLATFORM_ADMIN_ITEM: NavItem = { label: "Platform Admin", href: "/dashboard/admin", icon: "🛡️" };

export const NAV_GROUPS: NavGroup[] = [
  {
    key: "define",
    label: TIER_DEFINE,
    items: [
      { label: "Brands", href: "/dashboard/brands", icon: "🏢" },
      { label: "Brand Book", href: "/dashboard/brand-book", icon: "📖" },
      { label: "Avatar Personas", href: "/dashboard/personas", icon: "🎭" },
      { label: "Offers", href: "/dashboard/offers", icon: "🎁" },
    ],
  },
  {
    key: "reach",
    label: TIER_REACH,
    items: [
      { label: "Leads", href: "/dashboard/leads", icon: "🧲", subGroup: SUB_CAPTURE },
      { label: "Forms", href: "/dashboard/forms", icon: "📋" },
      { label: "CRM", href: "/dashboard/crm", icon: "👥", subGroup: SUB_COMMUNICATE },
      { label: "Campaigns", href: "/dashboard/campaigns", icon: "🚀" },
      { label: "Emails", href: "/dashboard/emails", icon: "✉️" },
      { label: "Sequences", href: "/dashboard/sequences", icon: "🔁" },
      { label: "Content", href: "/dashboard/content", icon: "📝", subGroup: SUB_PUBLISH },
      { label: "Media", href: "/dashboard/media", icon: "🎬" },
      { label: "Pitch Videos", href: "/dashboard/pitch-videos", icon: "🎥", minRole: "editor" },
      { label: "Social", href: "/dashboard/social", icon: "📣" },
      { label: "Scheduler", href: "/dashboard/scheduler", icon: "📅" },
    ],
  },
  {
    key: "govern",
    label: TIER_GOVERN,
    items: [
      APPROVALS_ITEM,
      { label: "Analytics", href: "/dashboard/analytics", icon: "📈" },
    ],
  },
];

/** Utility cluster at the sidebar bottom — account plumbing, not workflow. */
export const UTILITY_ITEMS: NavItem[] = [
  { label: "Help & FAQ", href: "/dashboard/help", icon: "❓" },
  { label: "Settings", href: "/dashboard/settings", icon: "⚙️", minRole: "owner" },
  { label: "Profile", href: "/dashboard/profile", icon: "👤" },
];

/** Flat view of every routable item (route guards, breadcrumbs, tests). */
export const NAV_ITEMS: NavItem[] = [
  OVERVIEW_ITEM,
  ...NAV_GROUPS.flatMap((g) => g.items),
  ...UTILITY_ITEMS,
];
