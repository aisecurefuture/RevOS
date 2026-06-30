"use client";

import { useEffect, useState } from "react";

import { PageHeader } from "@/components/PageHeader";
import { Button } from "@/components/ui/Button";
import { Card, CardTitle } from "@/components/ui/Card";
import { Spinner } from "@/components/ui/Spinner";
import { ApiError } from "@/lib/api";
import { useBrand } from "@/lib/brand";
import { integrationsApi } from "@/lib/resources";
import type { IntegrationStatus } from "@/lib/types";

function Dot({ on }: { on: boolean }) {
  return (
    <span
      className={`inline-block h-2.5 w-2.5 rounded-full ${on ? "bg-green-500" : "bg-slate-300"}`}
    />
  );
}

function Row({ label, on, note }: { label: string; on: boolean; note?: string }) {
  return (
    <li className="flex items-center justify-between py-1.5 text-sm">
      <span className="text-slate-700">{label}</span>
      <span className="flex items-center gap-2 text-xs text-slate-400">
        {note ?? (on ? "connected" : "not configured")}
        <Dot on={on} />
      </span>
    </li>
  );
}

export default function SettingsPage() {
  const { selectedBrandId } = useBrand();
  const [status, setStatus] = useState<IntegrationStatus | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    integrationsApi
      .status()
      .then(setStatus)
      .catch((e) => setError(e instanceof ApiError ? e.message : "Failed to load integrations"))
      .finally(() => setLoading(false));
  }, []);

  return (
    <>
      <PageHeader
        title="Settings"
        description="Integrations & exports. Everything degrades gracefully when keys are absent."
      />
      {error ? (
        <div className="mb-4 rounded-lg bg-red-50 px-3 py-2 text-sm text-red-700">{error}</div>
      ) : null}

      {loading || !status ? (
        <Spinner />
      ) : (
        <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
          <Card>
            <CardTitle>Core integrations</CardTitle>
            <ul className="divide-y divide-slate-100">
              <Row label="Resend (email)" on={status.email}
                   note={status.email_live ? "live" : status.email ? "test mode" : "not configured"} />
              <Row label="Stripe (payments)" on={status.stripe} />
              <Row label="AI provider" on={status.ai} />
              <Row label="S3 storage" on={status.s3} />
              <Row label="Calendly" on={status.calendly} />
              <Row label="Notion" on={status.notion} />
              <Row label="Zapier / Make" on={status.zapier} />
              <Row label="Bitly" on={status.bitly} />
              <Row label="Google Sheets" on={status.google_sheets} />
            </ul>
          </Card>

          <Card>
            <CardTitle>Social platforms</CardTitle>
            <ul className="divide-y divide-slate-100">
              {Object.entries(status.social).map(([platform, on]) => (
                <Row key={platform} label={platform} on={on}
                     note={on ? "live API" : "draft / copy-paste"} />
              ))}
            </ul>
          </Card>

          <Card>
            <CardTitle>Privacy-friendly analytics</CardTitle>
            <ul className="divide-y divide-slate-100">
              <Row label="Plausible" on={!!status.analytics.plausible_domain}
                   note={status.analytics.plausible_domain ?? "not configured"} />
              <Row label="PostHog" on={!!status.analytics.posthog_key} />
              <Row label="Google Analytics" on={!!status.analytics.ga_measurement_id}
                   note={status.analytics.ga_measurement_id ?? "not configured"} />
            </ul>
          </Card>

          <Card>
            <CardTitle>Exports</CardTitle>
            <p className="mb-3 text-sm text-slate-500">
              Export contacts for Airtable / Google Sheets (CSV) or Notion (Markdown).
            </p>
            <div className="flex gap-2">
              <Button
                variant="secondary"
                onClick={() => void integrationsApi.exportContacts("csv", selectedBrandId)}
              >
                Contacts CSV
              </Button>
              <Button
                variant="secondary"
                onClick={() => void integrationsApi.exportContacts("notion", selectedBrandId)}
              >
                Contacts → Notion
              </Button>
            </div>
          </Card>
        </div>
      )}
    </>
  );
}
