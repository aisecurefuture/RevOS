"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useEffect, useState } from "react";

import { ApiError } from "@/lib/api";
import { publicCreatorApi } from "@/lib/resources";
import type { PublicCreatorPage } from "@/lib/types";

const TIER_GLOW: Record<string, string> = {
  "Top-Rated": "from-emerald-400 to-teal-400",
  Trusted: "from-sky-400 to-violet-400",
  Growing: "from-amber-400 to-orange-400",
  New: "from-white/30 to-white/10",
};

function pct(v: number | null | undefined): string {
  return v == null ? "—" : `${Math.round(v * 100)}%`;
}

export default function PublicCreatorPageRoute() {
  const params = useParams<{ slug: string }>();
  const [page, setPage] = useState<PublicCreatorPage | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    publicCreatorApi
      .get(params.slug)
      .then(setPage)
      .catch((e) => setError(e instanceof ApiError ? e.message : "This page couldn't be found."));
  }, [params.slug]);

  return (
    <div className="min-h-screen bg-[#0b0713] text-white">
      <div
        className="pointer-events-none fixed inset-0 opacity-60"
        style={{
          background:
            "radial-gradient(60rem 40rem at 15% -10%, rgba(129,92,255,0.35), transparent 60%)," +
            "radial-gradient(50rem 35rem at 110% 10%, rgba(236,72,153,0.25), transparent 55%)",
        }}
      />
      <div className="relative z-10 mx-auto max-w-2xl px-5 py-14 sm:px-8">
        {error ? (
          <div className="rounded-xl border border-red-500/30 bg-red-500/10 px-4 py-6 text-center text-red-200">
            {error}
          </div>
        ) : !page ? (
          <div className="animate-pulse text-center text-white/40">Loading…</div>
        ) : (
          <>
            <div className="mb-8 text-center">
              <div className="mx-auto mb-4 inline-flex h-16 w-16 items-center justify-center rounded-2xl bg-gradient-to-br from-violet-500 to-fuchsia-500 text-3xl">
                {page.display_name.charAt(0).toUpperCase()}
              </div>
              <h1 className="text-3xl font-bold tracking-tight sm:text-4xl">{page.display_name}</h1>
              {page.handle ? <p className="mt-1 text-white/50">{page.handle}</p> : null}
              {page.industry ? (
                <p className="mt-2 inline-block rounded-full border border-white/15 px-3 py-1 text-xs uppercase tracking-wide text-white/60">
                  {page.industry.replace(/_/g, " ")}
                </p>
              ) : null}
            </div>

            {page.reputation ? (
              <div className="mb-6 rounded-2xl border border-white/10 bg-white/[0.03] p-5 text-center">
                <div className={`mx-auto mb-2 inline-block bg-gradient-to-r ${TIER_GLOW[page.reputation.tier] ?? TIER_GLOW.New} bg-clip-text text-4xl font-bold text-transparent`}>
                  {page.reputation.tier}
                </div>
                <p className="text-sm text-white/60">
                  Reputation score {Math.round(page.reputation.overall)}/100
                  {page.reputation.percentile != null
                    ? ` · beats ${page.reputation.percentile}% of peers`
                    : ""}
                </p>
              </div>
            ) : null}

            {page.bio ? <p className="mb-6 text-center text-white/70">{page.bio}</p> : null}

            {(page.follower_count != null || page.engagement_rate != null || page.location || page.size_tier) ? (
              <div className="mb-6 grid grid-cols-2 gap-3 sm:grid-cols-4">
                {page.follower_count != null ? (
                  <div className="rounded-xl border border-white/10 bg-white/5 p-3 text-center">
                    <div className="text-xl font-bold">{page.follower_count.toLocaleString()}</div>
                    <div className="text-xs text-white/50">Followers</div>
                  </div>
                ) : null}
                {page.engagement_rate != null ? (
                  <div className="rounded-xl border border-white/10 bg-white/5 p-3 text-center">
                    <div className="text-xl font-bold">{pct(page.engagement_rate)}</div>
                    <div className="text-xs text-white/50">Engagement</div>
                  </div>
                ) : null}
                {page.location ? (
                  <div className="rounded-xl border border-white/10 bg-white/5 p-3 text-center">
                    <div className="text-sm font-semibold">{page.location}</div>
                    <div className="text-xs text-white/50">Based in</div>
                  </div>
                ) : null}
                {page.size_tier ? (
                  <div className="rounded-xl border border-white/10 bg-white/5 p-3 text-center capitalize">
                    <div className="text-sm font-semibold">{page.size_tier}</div>
                    <div className="text-xs text-white/50">Tier</div>
                  </div>
                ) : null}
              </div>
            ) : null}

            {page.engagement_benchmark ? (
              <p className="mb-6 text-center text-xs text-white/40">
                {page.engagement_benchmark.verdict === "above" ? "Above" : page.engagement_benchmark.verdict === "below" ? "Below" : "In line with"}{" "}
                the {page.engagement_benchmark.source === "industry_report" ? "industry" : "peer"} average of{" "}
                {(page.engagement_benchmark.cohort_avg * 100).toFixed(1)}%
                {page.engagement_benchmark.citation ? ` · ${page.engagement_benchmark.citation}` : ""}
              </p>
            ) : null}

            {page.topics.length > 0 ? (
              <div className="mb-6 flex flex-wrap justify-center gap-2">
                {page.topics.map((t) => (
                  <span key={t} className="rounded-full border border-white/15 px-3 py-1 text-xs text-white/70">
                    {t}
                  </span>
                ))}
              </div>
            ) : null}

            {page.certifications.length > 0 ? (
              <div className="mb-8">
                <h2 className="mb-2 text-center text-xs uppercase tracking-wide text-white/40">
                  Certifications
                </h2>
                <div className="space-y-2">
                  {page.certifications.map((c, i) => (
                    <div key={i} className="flex items-center justify-between rounded-lg border border-white/10 bg-white/[0.03] px-3 py-2 text-sm">
                      <span>{c.name}{c.issuer ? ` · ${c.issuer}` : ""}</span>
                      {c.verified ? (
                        <span className="rounded-full bg-emerald-500/20 px-2 py-0.5 text-xs text-emerald-300">
                          ✓ Verified
                        </span>
                      ) : null}
                    </div>
                  ))}
                </div>
              </div>
            ) : null}

            <div className="text-center">
              <Link
                href="/register"
                className="inline-block rounded-lg bg-gradient-to-r from-violet-500 to-fuchsia-500 px-6 py-3 text-sm font-semibold text-white hover:opacity-90"
              >
                Want to work with {page.display_name.split(" ")[0]}? Get started →
              </Link>
              <p className="mt-4 text-xs text-white/30">{page.view_count.toLocaleString()} people have viewed this page</p>
            </div>
          </>
        )}
      </div>
    </div>
  );
}
