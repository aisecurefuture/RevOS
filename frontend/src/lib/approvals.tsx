"use client";

// Pending-approvals count for the nav badge. Refreshes on route change and
// on a slow poll — approvals are minutes-scale, not real-time, and the
// endpoint is a bare COUNT so this stays cheap.

import { usePathname } from "next/navigation";
import { useEffect, useState } from "react";

import { approvalsApi } from "./resources";

const POLL_MS = 60_000;

export function usePendingApprovals(): { pendingCount: number } {
  const [pendingCount, setPendingCount] = useState(0);
  const pathname = usePathname();

  useEffect(() => {
    let cancelled = false;
    const refresh = () => {
      approvalsApi
        .pendingCount()
        .then((r) => {
          if (!cancelled) setPendingCount(r.pending);
        })
        .catch(() => {
          /* unauthenticated or transient — badge just stays as-is */
        });
    };
    refresh();
    const t = setInterval(refresh, POLL_MS);
    return () => {
      cancelled = true;
      clearInterval(t);
    };
  }, [pathname]);

  return { pendingCount };
}
