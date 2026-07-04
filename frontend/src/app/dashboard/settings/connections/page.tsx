"use client";

import { useRouter, useSearchParams } from "next/navigation";
import { Suspense, useCallback, useEffect, useState } from "react";

import { PageHeader } from "@/components/PageHeader";
import { Button } from "@/components/ui/Button";
import { Spinner } from "@/components/ui/Spinner";
import { ApiError, socialApi, type SocialConnection } from "@/lib/api";

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

const PLATFORM_META = {
  facebook: { label: "Facebook Pages", icon: "📘", color: "text-blue-600" },
  instagram: { label: "Instagram Business", icon: "📷", color: "text-pink-600" },
  threads: { label: "Threads", icon: "🧵", color: "text-slate-700" },
  youtube: { label: "YouTube", icon: "📺", color: "text-red-600" },
  twitter: { label: "X", icon: "𝕏", color: "text-slate-900" },
  linkedin: { label: "LinkedIn", icon: "💼", color: "text-blue-700" },
} as const;

const STATUS_BADGE: Record<string, string> = {
  active: "bg-green-50 text-green-700",
  error: "bg-red-50 text-red-700",
  expired: "bg-amber-50 text-amber-700",
  revoked: "bg-slate-100 text-slate-500",
};

function groupConnections(list: SocialConnection[]) {
  const groups: Partial<Record<SocialConnection["platform"], SocialConnection[]>> = {};
  for (const c of list) {
    if (!groups[c.platform]) groups[c.platform] = [];
    groups[c.platform]!.push(c);
  }
  return groups;
}

// ---------------------------------------------------------------------------
// Platform section
// ---------------------------------------------------------------------------

interface PlatformSectionProps {
  platform: SocialConnection["platform"];
  connections: SocialConnection[];
  onConnect: (platform: string) => void;
  onDisconnect: (id: string) => void;
  connecting: string | null;
  disconnecting: string | null;
}

function PlatformSection({
  platform,
  connections,
  onConnect,
  onDisconnect,
  connecting,
  disconnecting,
}: PlatformSectionProps) {
  const meta = PLATFORM_META[platform];

  return (
    <div className="rounded-xl border border-slate-200 bg-white p-5">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <span className="text-xl">{meta.icon}</span>
          <span className={`font-semibold ${meta.color}`}>{meta.label}</span>
          {connections.length > 0 && (
            <span className="rounded-full bg-slate-100 px-2 py-0.5 text-xs text-slate-500">
              {connections.length}
            </span>
          )}
        </div>
        <Button
          variant="secondary"
          onClick={() => onConnect(platform === "instagram" ? "facebook" : platform)}
          disabled={connecting !== null}
        >
          {connecting === platform ? "Redirecting…" : `Connect ${meta.label.split(" ")[0]}`}
        </Button>
      </div>

      {connections.length > 0 && (
        <ul className="mt-4 divide-y divide-slate-100">
          {connections.map((conn) => (
            <li key={conn.id} className="flex items-center justify-between py-3">
              <div>
                <p className="text-sm font-medium text-slate-800">
                  {conn.display_name ?? conn.handle ?? conn.external_id}
                </p>
                {conn.handle && conn.handle !== conn.display_name && (
                  <p className="text-xs text-slate-400">@{conn.handle}</p>
                )}
                {conn.expires_at && (
                  <p className="text-xs text-slate-400">
                    Expires {new Date(conn.expires_at).toLocaleDateString()}
                  </p>
                )}
              </div>
              <div className="flex items-center gap-3">
                <span className={`rounded-full px-2 py-0.5 text-xs font-medium ${STATUS_BADGE[conn.status] ?? ""}`}>
                  {conn.status}
                </span>
                <button
                  onClick={() => onDisconnect(conn.id)}
                  disabled={disconnecting === conn.id}
                  className="text-xs text-slate-400 hover:text-red-600 disabled:opacity-50"
                >
                  {disconnecting === conn.id ? "Removing…" : "Disconnect"}
                </button>
              </div>
            </li>
          ))}
        </ul>
      )}

      {connections.length === 0 && (
        <p className="mt-3 text-sm text-slate-400">No accounts connected yet.</p>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Main page
// ---------------------------------------------------------------------------

function ConnectionsInner() {
  const searchParams = useSearchParams();
  const router = useRouter();

  const [connections, setConnections] = useState<SocialConnection[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [connecting, setConnecting] = useState<string | null>(null);
  const [disconnecting, setDisconnecting] = useState<string | null>(null);
  const [banner, setBanner] = useState<{ type: "success" | "error"; message: string } | null>(null);

  // Handle OAuth redirect params
  useEffect(() => {
    const connected = searchParams.get("connected");
    const count = searchParams.get("count");
    const err = searchParams.get("error");
    if (connected && count) {
      setBanner({
        type: "success",
        message: `Connected ${count} ${connected} account${Number(count) !== 1 ? "s" : ""} successfully.`,
      });
      router.replace("/dashboard/settings/connections");
    } else if (err) {
      setBanner({
        type: "error",
        message: `Connection failed: ${err.replace(/_/g, " ")}. Please try again.`,
      });
      router.replace("/dashboard/settings/connections");
    }
  }, [searchParams, router]);

  const load = useCallback(async () => {
    try {
      const data = await socialApi.list();
      setConnections(data);
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Failed to load connections.");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { void load(); }, [load]);

  async function handleConnect(platform: string) {
    setConnecting(platform);
    try {
      const { url } = await socialApi.connectUrl(platform);
      window.location.href = url;
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Could not start connection.");
      setConnecting(null);
    }
  }

  async function handleDisconnect(id: string) {
    if (!confirm("Disconnect this account? Any scheduled posts using it will fail.")) return;
    setDisconnecting(id);
    try {
      await socialApi.disconnect(id);
      setConnections((prev) => prev.filter((c) => c.id !== id));
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Failed to disconnect.");
    } finally {
      setDisconnecting(null);
    }
  }

  const groups = groupConnections(connections);
  const platforms: SocialConnection["platform"][] = ["facebook", "instagram", "threads", "youtube", "twitter", "linkedin"];

  return (
    <>
      <PageHeader
        title="Social Connections"
        description="Connect your Facebook Pages, Instagram Business Accounts, and Threads profile."
      />

      {banner && (
        <div className={`mb-4 rounded-lg px-4 py-3 text-sm ${
          banner.type === "success"
            ? "bg-green-50 text-green-800 border border-green-200"
            : "bg-red-50 text-red-800 border border-red-200"
        }`}>
          {banner.message}
        </div>
      )}

      {error && (
        <div className="mb-4 rounded-lg bg-red-50 px-4 py-3 text-sm text-red-700 border border-red-200">
          {error}
        </div>
      )}

      {loading ? (
        <Spinner />
      ) : (
        <div className="space-y-4">
          {platforms.map((platform) => (
            <PlatformSection
              key={platform}
              platform={platform}
              connections={groups[platform] ?? []}
              onConnect={handleConnect}
              onDisconnect={handleDisconnect}
              connecting={connecting}
              disconnecting={disconnecting}
            />
          ))}

          <p className="text-center text-xs text-slate-400 pt-2">
            Approval-first — no content is published without your explicit sign-off.
          </p>
        </div>
      )}
    </>
  );
}

export default function ConnectionsPage() {
  return (
    <Suspense fallback={<Spinner />}>
      <ConnectionsInner />
    </Suspense>
  );
}
