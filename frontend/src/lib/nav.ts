// Sidebar navigation config. Each item maps to a dashboard route. The `roles`
// field (optional) hides items from insufficient roles in later modules.

import type { Role } from "./types";

export interface NavItem {
  label: string;
  href: string;
  icon: string; // simple emoji glyphs keep the shell dependency-free
  minRole?: Role;
}

export const NAV_ITEMS: NavItem[] = [
  { label: "Overview", href: "/dashboard", icon: "📊" },
  { label: "Brands", href: "/dashboard/brands", icon: "🏢" },
  { label: "Offers", href: "/dashboard/offers", icon: "🎁" },
  { label: "Leads", href: "/dashboard/leads", icon: "🧲" },
  { label: "Forms", href: "/dashboard/forms", icon: "📋" },
  { label: "CRM", href: "/dashboard/crm", icon: "👥" },
  { label: "Campaigns", href: "/dashboard/campaigns", icon: "🚀" },
  { label: "Emails", href: "/dashboard/emails", icon: "✉️" },
  { label: "Sequences", href: "/dashboard/sequences", icon: "🔁" },
  { label: "Content", href: "/dashboard/content", icon: "📝" },
  { label: "Media", href: "/dashboard/media", icon: "🎬" },
  { label: "Social", href: "/dashboard/social", icon: "📣" },
  { label: "Analytics", href: "/dashboard/analytics", icon: "📈" },
  { label: "Approvals", href: "/dashboard/approvals", icon: "✅" },
  { label: "Settings", href: "/dashboard/settings", icon: "⚙️", minRole: "owner" },
  { label: "Profile", href: "/dashboard/profile", icon: "👤" },
];
