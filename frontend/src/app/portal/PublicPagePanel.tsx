"use client";

import { useCallback, useEffect, useState } from "react";

import { ApiError } from "@/lib/api";
import { qrCodeImageUrl } from "@/lib/qrcode";
import { marketplaceApi } from "@/lib/resources";
import { PUBLIC_CREATOR_FIELDS } from "@/lib/types";
import type { MatchCreator, PublicPageSettings } from "@/lib/types";

export function PublicPagePanel({ creator }: { creator: MatchCreator }) {
  const [settings, setSettings] = useState<PublicPageSettings | null>(null);
  const [fields, setFields] = useState<Set<string>>(new Set());
  const [slugInput, setSlugInput] = useState("");
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [copied, setCopied] = useState(false);

  const load = useCallback(async () => {
    try {
      const s = await marketplaceApi.getPublicPageSettings(creator.id);
      setSettings(s);
      setFields(new Set(s.fields));
      setSlugInput(s.slug ?? "");
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Failed to load your public page settings");
    }
  }, [creator.id]);

  useEffect(() => {
    void load();
  }, [load]);

  function toggleField(key: string) {
    setFields((prev) => {
      const next = new Set(prev);
      if (next.has(key)) next.delete(key);
      else next.add(key);
      return next;
    });
  }

  async function save(enabled: boolean) {
    setSaving(true);
    setError(null);
    try {
      const updated = await marketplaceApi.updatePublicPageSettings(creator.id, {
        enabled,
        slug: slugInput.trim() || undefined,
        fields: Array.from(fields),
      });
      setSettings(updated);
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Failed to save");
    } finally {
      setSaving(false);
    }
  }

  async function copyLink() {
    if (!settings?.share_url) return;
    await navigator.clipboard.writeText(settings.share_url);
    setCopied(true);
    setTimeout(() => setCopied(false), 1500);
  }

  if (!settings) return null;

  return (
    <div className="rounded-2xl border border-white/10 bg-white/[0.03] p-6">
      <div className="flex items-center justify-between">
        <h2 className="text-lg font-semibold">Your public page &amp; QR code</h2>
        <button
          type="button"
          onClick={() => void save(!settings.enabled)}
          disabled={saving}
          className={`relative h-6 w-11 shrink-0 rounded-full transition-colors disabled:opacity-50 ${
            settings.enabled ? "bg-gradient-to-r from-violet-500 to-fuchsia-500" : "bg-white/15"
          }`}
        >
          <span
            className={`absolute top-0.5 h-5 w-5 rounded-full bg-white transition-transform ${
              settings.enabled ? "translate-x-5" : "translate-x-0.5"
            }`}
          />
        </button>
      </div>
      <p className="mt-1 text-sm text-white/50">
        A no-login page you control — perfect for a QR code on business cards or your social bio.
        Separate from marketplace discoverability: you pick exactly what shows.
      </p>

      {error ? <p className="mt-3 text-sm text-red-300">{error}</p> : null}

      {settings.enabled ? (
        <div className="mt-5 grid gap-6 sm:grid-cols-[auto_1fr]">
          {settings.share_url ? (
            <div className="flex flex-col items-center gap-2">
              <div className="rounded-xl bg-white p-2">
                {/* eslint-disable-next-line @next/next/no-img-element */}
                <img src={qrCodeImageUrl(settings.share_url)} alt="QR code to your public page" width={160} height={160} />
              </div>
              <a
                href={qrCodeImageUrl(settings.share_url, 800)}
                download="my-revos-qr.png"
                className="text-xs text-violet-300 hover:text-violet-200"
              >
                Download PNG
              </a>
            </div>
          ) : null}

          <div className="space-y-4">
            <div>
              <label className="mb-1 block text-xs font-medium uppercase tracking-wide text-white/40">
                Your link
              </label>
              <div className="flex gap-2">
                <input
                  value={slugInput}
                  onChange={(e) => setSlugInput(e.target.value)}
                  placeholder="your-name"
                  className="w-full rounded-lg border border-white/15 bg-white/5 px-3 py-2 text-sm placeholder:text-white/30 focus:border-violet-400 focus:outline-none"
                />
                <button
                  type="button"
                  onClick={() => void save(true)}
                  disabled={saving}
                  className="shrink-0 rounded-lg border border-white/15 px-3 py-2 text-xs font-medium hover:border-white/30 disabled:opacity-50"
                >
                  Update
                </button>
              </div>
              {settings.share_url ? (
                <div className="mt-2 flex items-center gap-2 text-xs text-white/50">
                  <span className="truncate">{settings.share_url}</span>
                  <button type="button" onClick={() => void copyLink()} className="shrink-0 text-violet-300 hover:text-violet-200">
                    {copied ? "Copied!" : "Copy"}
                  </button>
                </div>
              ) : null}
              <p className="mt-1 text-xs text-white/30">{settings.view_count.toLocaleString()} views so far</p>
            </div>

            <div>
              <label className="mb-2 block text-xs font-medium uppercase tracking-wide text-white/40">
                What to show
              </label>
              <div className="grid grid-cols-2 gap-2">
                {PUBLIC_CREATOR_FIELDS.map((f) => (
                  <label key={f.key} className="flex items-center gap-2 text-sm text-white/70">
                    <input
                      type="checkbox"
                      checked={fields.has(f.key)}
                      onChange={() => toggleField(f.key)}
                      className="rounded border-white/30 bg-white/5"
                    />
                    {f.label}
                  </label>
                ))}
              </div>
              <button
                type="button"
                onClick={() => void save(true)}
                disabled={saving}
                className="mt-3 rounded-lg bg-gradient-to-r from-violet-500 to-fuchsia-500 px-4 py-2 text-xs font-semibold hover:opacity-90 disabled:opacity-50"
              >
                {saving ? "Saving…" : "Save what's shown"}
              </button>
            </div>
          </div>
        </div>
      ) : null}
    </div>
  );
}
