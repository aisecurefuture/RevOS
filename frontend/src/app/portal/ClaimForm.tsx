"use client";

import { useState } from "react";

import { ApiError } from "@/lib/api";
import { marketplaceApi } from "@/lib/resources";

function extractToken(input: string): string {
  const trimmed = input.trim();
  try {
    const url = new URL(trimmed);
    const t = url.searchParams.get("token");
    if (t) return t;
  } catch {
    // not a URL — treat the whole input as the token
  }
  return trimmed;
}

export function ClaimForm({ onClaimed }: { onClaimed: () => void }) {
  const [input, setInput] = useState("");
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);

  async function claim(e: React.FormEvent) {
    e.preventDefault();
    const token = extractToken(input);
    if (!token) return;
    setSaving(true);
    setError(null);
    try {
      const creator = await marketplaceApi.claimCreator(token);
      setSuccess(`You're verified as ${creator.display_name}! Loading your dashboard…`);
      setTimeout(onClaimed, 900);
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "That link didn't work — ask for a fresh invite.");
      setSaving(false);
    }
  }

  return (
    <div className="mx-auto max-w-lg py-16 text-center">
      <div className="mb-6 inline-flex h-16 w-16 items-center justify-center rounded-2xl bg-gradient-to-br from-violet-500 to-fuchsia-500 text-3xl shadow-[0_0_60px_-10px_rgba(168,85,247,0.6)]">
        ✦
      </div>
      <h1 className="mb-2 text-3xl font-bold tracking-tight sm:text-4xl">
        Your creator profile, unlocked.
      </h1>
      <p className="mx-auto mb-8 max-w-sm text-white/60">
        Track your reputation, see how you stack up against peers, and jump on brand
        collaborations the moment they land — all from one dashboard.
      </p>

      <form onSubmit={claim} className="mx-auto max-w-md rounded-2xl border border-white/10 bg-white/5 p-5 backdrop-blur">
        <label className="mb-2 block text-left text-xs font-medium uppercase tracking-wide text-white/50">
          Paste your claim link or code
        </label>
        <input
          value={input}
          onChange={(e) => setInput(e.target.value)}
          placeholder="https://app.revos360.com/claim-creator?token=…"
          className="w-full rounded-lg border border-white/15 bg-white/5 px-3 py-2.5 text-sm text-white placeholder:text-white/30 focus:border-violet-400 focus:outline-none focus:ring-1 focus:ring-violet-400"
        />
        {error ? <p className="mt-2 text-left text-sm text-red-300">{error}</p> : null}
        {success ? <p className="mt-2 text-left text-sm text-emerald-300">{success}</p> : null}
        <button
          type="submit"
          disabled={saving || !input.trim()}
          className="mt-4 w-full rounded-lg bg-gradient-to-r from-violet-500 to-fuchsia-500 px-4 py-2.5 text-sm font-semibold text-white transition hover:opacity-90 disabled:opacity-50"
        >
          {saving ? "Verifying…" : "Claim my profile"}
        </button>
      </form>
      <p className="mt-6 text-xs text-white/40">
        Don&apos;t have a link? Ask the agency or brand who added you to send one from their
        Marketplace → My roster page.
      </p>
    </div>
  );
}
