"use client";

import { useCallback, useEffect, useState } from "react";

import { PageHeader } from "@/components/PageHeader";
import { Button } from "@/components/ui/Button";
import { Card, CardTitle } from "@/components/ui/Card";
import { Spinner } from "@/components/ui/Spinner";
import {
  ApiError,
  integrationCredentialsApi as api,
  type IntegrationCredential,
} from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { useBrand } from "@/lib/brand";

function findCred(creds: IntegrationCredential[], provider: string) {
  return creds.find((c) => c.provider === provider) ?? null;
}

// ---------------------------------------------------------------------------
// Calendly
// ---------------------------------------------------------------------------

function CalendlyCard({ cred, onSaved, onRemoved }: {
  cred: IntegrationCredential | null;
  onSaved: () => void;
  onRemoved: () => void;
}) {
  const [url, setUrl] = useState((cred?.config.scheduling_url as string) ?? "");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function save() {
    setBusy(true);
    setError(null);
    try {
      await api.saveCalendly(url);
      onSaved();
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Save failed");
    } finally {
      setBusy(false);
    }
  }

  async function remove() {
    setBusy(true);
    try {
      await api.remove("calendly");
      onRemoved();
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Remove failed");
    } finally {
      setBusy(false);
    }
  }

  return (
    <Card>
      <CardTitle>📅 Calendly</CardTitle>
      <p className="mb-3 text-xs text-slate-400">
        Your public scheduling link — surfaced as a &quot;Book a call&quot; link
        elsewhere in RevOS. (A built-in scheduler is coming; this is a lightweight
        placeholder until then.)
      </p>
      <div className="flex gap-2">
        <input
          value={url}
          onChange={(e) => setUrl(e.target.value)}
          placeholder="https://calendly.com/you/intro-call"
          className="grow rounded-lg border border-slate-300 px-3 py-2 text-sm"
        />
        <Button onClick={() => void save()} disabled={busy || !url.trim()}>
          Save
        </Button>
        {cred ? (
          <Button variant="secondary" onClick={() => void remove()} disabled={busy}>
            Remove
          </Button>
        ) : null}
      </div>
      {error ? <p className="mt-2 text-xs text-red-600">{error}</p> : null}
    </Card>
  );
}

// ---------------------------------------------------------------------------
// Notion
// ---------------------------------------------------------------------------

function NotionCard({ cred, brandId, onSaved, onRemoved }: {
  cred: IntegrationCredential | null;
  brandId: string | null;
  onSaved: () => void;
  onRemoved: () => void;
}) {
  const [apiKey, setApiKey] = useState("");
  const [databaseId, setDatabaseId] = useState((cred?.config.database_id as string) ?? "");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  async function save() {
    setBusy(true);
    setError(null);
    try {
      await api.saveNotion(apiKey, databaseId);
      setApiKey("");
      onSaved();
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Save failed");
    } finally {
      setBusy(false);
    }
  }

  async function remove() {
    setBusy(true);
    try {
      await api.remove("notion");
      onRemoved();
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Remove failed");
    } finally {
      setBusy(false);
    }
  }

  async function push() {
    setBusy(true);
    setError(null);
    setNotice(null);
    try {
      const r = await api.pushContactsToNotion(brandId);
      setNotice(`Pushed ${r.pushed} contact(s) to Notion.`);
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Push failed");
    } finally {
      setBusy(false);
    }
  }

  return (
    <Card>
      <CardTitle>📝 Notion</CardTitle>
      <p className="mb-3 text-xs text-slate-400">
        Push CRM contacts as pages into a Notion database. Share your database with
        the integration first, then paste its integration token and database ID.
      </p>
      {cred ? (
        <div className="mb-3 flex items-center gap-2">
          <span className="rounded-full bg-green-100 px-2 py-0.5 text-xs font-medium text-green-700">
            Connected
          </span>
          <Button variant="secondary" onClick={() => void push()} disabled={busy}>
            {busy ? "Pushing…" : "Push contacts to Notion"}
          </Button>
          <Button variant="secondary" onClick={() => void remove()} disabled={busy}>
            Remove
          </Button>
        </div>
      ) : (
        <div className="space-y-2">
          <input
            type="password"
            value={apiKey}
            onChange={(e) => setApiKey(e.target.value)}
            placeholder="Integration token (secret_...)"
            className="w-full rounded-lg border border-slate-300 px-3 py-2 text-sm"
          />
          <input
            value={databaseId}
            onChange={(e) => setDatabaseId(e.target.value)}
            placeholder="Database ID"
            className="w-full rounded-lg border border-slate-300 px-3 py-2 text-sm"
          />
          <Button onClick={() => void save()} disabled={busy || !apiKey.trim() || !databaseId.trim()}>
            Save
          </Button>
        </div>
      )}
      {notice ? <p className="mt-2 text-xs text-green-700">{notice}</p> : null}
      {error ? <p className="mt-2 text-xs text-red-600">{error}</p> : null}
    </Card>
  );
}

// ---------------------------------------------------------------------------
// Bitly
// ---------------------------------------------------------------------------

function BitlyCard({ cred, onSaved, onRemoved }: {
  cred: IntegrationCredential | null;
  onSaved: () => void;
  onRemoved: () => void;
}) {
  const [token, setToken] = useState("");
  const [longUrl, setLongUrl] = useState("");
  const [shortUrl, setShortUrl] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function save() {
    setBusy(true);
    setError(null);
    try {
      await api.saveBitly(token);
      setToken("");
      onSaved();
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Save failed");
    } finally {
      setBusy(false);
    }
  }

  async function remove() {
    setBusy(true);
    try {
      await api.remove("bitly");
      onRemoved();
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Remove failed");
    } finally {
      setBusy(false);
    }
  }

  async function shorten() {
    setBusy(true);
    setError(null);
    setShortUrl(null);
    try {
      const r = await api.shortenLink(longUrl);
      setShortUrl(r.short_url);
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Shorten failed");
    } finally {
      setBusy(false);
    }
  }

  return (
    <Card>
      <CardTitle>🔗 Bitly</CardTitle>
      <p className="mb-3 text-xs text-slate-400">Shorten links for social posts and emails.</p>
      {cred ? (
        <div className="space-y-2">
          <div className="flex items-center gap-2">
            <span className="rounded-full bg-green-100 px-2 py-0.5 text-xs font-medium text-green-700">
              Connected
            </span>
            <Button variant="secondary" onClick={() => void remove()} disabled={busy}>
              Remove
            </Button>
          </div>
          <div className="flex gap-2">
            <input
              value={longUrl}
              onChange={(e) => setLongUrl(e.target.value)}
              placeholder="Paste a long URL to shorten…"
              className="grow rounded-lg border border-slate-300 px-3 py-2 text-sm"
            />
            <Button onClick={() => void shorten()} disabled={busy || !longUrl.trim()}>
              Shorten
            </Button>
          </div>
          {shortUrl ? (
            <p className="text-sm text-slate-700">
              <a href={shortUrl} target="_blank" rel="noreferrer" className="text-brand underline">
                {shortUrl}
              </a>
            </p>
          ) : null}
        </div>
      ) : (
        <div className="flex gap-2">
          <input
            type="password"
            value={token}
            onChange={(e) => setToken(e.target.value)}
            placeholder="Access token"
            className="grow rounded-lg border border-slate-300 px-3 py-2 text-sm"
          />
          <Button onClick={() => void save()} disabled={busy || !token.trim()}>
            Save
          </Button>
        </div>
      )}
      {error ? <p className="mt-2 text-xs text-red-600">{error}</p> : null}
    </Card>
  );
}

// ---------------------------------------------------------------------------
// Google Sheets
// ---------------------------------------------------------------------------

function GoogleSheetsCard({ cred, brandId, onSaved, onRemoved }: {
  cred: IntegrationCredential | null;
  brandId: string | null;
  onSaved: () => void;
  onRemoved: () => void;
}) {
  const [json, setJson] = useState("");
  const [spreadsheetId, setSpreadsheetId] = useState((cred?.config.spreadsheet_id as string) ?? "");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  async function save() {
    setBusy(true);
    setError(null);
    try {
      await api.saveGoogleSheets(json, spreadsheetId);
      setJson("");
      onSaved();
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Save failed");
    } finally {
      setBusy(false);
    }
  }

  async function remove() {
    setBusy(true);
    try {
      await api.remove("google_sheets");
      onRemoved();
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Remove failed");
    } finally {
      setBusy(false);
    }
  }

  async function push() {
    setBusy(true);
    setError(null);
    setNotice(null);
    try {
      const r = await api.pushContactsToSheets(brandId);
      setNotice(`Appended ${r.pushed} contact(s) to your sheet.`);
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Push failed");
    } finally {
      setBusy(false);
    }
  }

  return (
    <Card>
      <CardTitle>📊 Google Sheets</CardTitle>
      <p className="mb-3 text-xs text-slate-400">
        Push CRM contacts as rows into a spreadsheet. Create a Google Cloud
        service account, share the target spreadsheet with its email
        (Editor access), then paste the key JSON below.
      </p>
      {cred ? (
        <div className="flex items-center gap-2">
          <span className="rounded-full bg-green-100 px-2 py-0.5 text-xs font-medium text-green-700">
            Connected
          </span>
          <Button variant="secondary" onClick={() => void push()} disabled={busy}>
            {busy ? "Pushing…" : "Push contacts to Sheet"}
          </Button>
          <Button variant="secondary" onClick={() => void remove()} disabled={busy}>
            Remove
          </Button>
        </div>
      ) : (
        <div className="space-y-2">
          <textarea
            value={json}
            onChange={(e) => setJson(e.target.value)}
            placeholder='Paste service-account JSON key: {"client_email": ..., "private_key": ..., "token_uri": ...}'
            rows={4}
            className="w-full rounded-lg border border-slate-300 px-3 py-2 font-mono text-xs"
          />
          <input
            value={spreadsheetId}
            onChange={(e) => setSpreadsheetId(e.target.value)}
            placeholder="Spreadsheet ID (from the sheet's URL)"
            className="w-full rounded-lg border border-slate-300 px-3 py-2 text-sm"
          />
          <Button onClick={() => void save()} disabled={busy || !json.trim() || !spreadsheetId.trim()}>
            Save
          </Button>
        </div>
      )}
      {notice ? <p className="mt-2 text-xs text-green-700">{notice}</p> : null}
      {error ? <p className="mt-2 text-xs text-red-600">{error}</p> : null}
    </Card>
  );
}

// ---------------------------------------------------------------------------
// Zapier
// ---------------------------------------------------------------------------

function ZapierCard({ cred, onSaved }: {
  cred: IntegrationCredential | null;
  onSaved: () => void;
}) {
  const [outboundUrl, setOutboundUrl] = useState((cred?.config.outbound_webhook_url as string) ?? "");
  const [inboundUrl, setInboundUrl] = useState<string | null>(null);
  const [revealedSecret, setRevealedSecret] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function save() {
    setBusy(true);
    setError(null);
    try {
      const r = await api.saveZapier(outboundUrl || null);
      setInboundUrl(r.inbound_webhook_url);
      if (r.inbound_secret) setRevealedSecret(r.inbound_secret);
      onSaved();
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Save failed");
    } finally {
      setBusy(false);
    }
  }

  async function regenerate() {
    if (!confirm("Regenerate the inbound secret? Your existing Zapier trigger will stop working until you update it.")) return;
    setBusy(true);
    setError(null);
    try {
      const r = await api.regenerateZapierSecret();
      setRevealedSecret(r.inbound_secret);
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Regenerate failed");
    } finally {
      setBusy(false);
    }
  }

  return (
    <Card>
      <CardTitle>⚡ Zapier / Make</CardTitle>
      <p className="mb-3 text-xs text-slate-400">
        Outbound: fires a <code>new_lead</code> event to your Zap/scenario whenever
        someone submits a public form. Inbound: create a contact in RevOS from any
        Zap/scenario using the signed URL below.
      </p>

      <div className="mb-3">
        <label className="mb-1 block text-xs font-medium text-slate-600">
          Outbound webhook URL (optional)
        </label>
        <div className="flex gap-2">
          <input
            value={outboundUrl}
            onChange={(e) => setOutboundUrl(e.target.value)}
            placeholder="https://hooks.zapier.com/hooks/catch/..."
            className="grow rounded-lg border border-slate-300 px-3 py-2 text-sm"
          />
          <Button onClick={() => void save()} disabled={busy}>
            Save
          </Button>
        </div>
      </div>

      {cred ? (
        <div className="rounded-lg bg-slate-50 border border-slate-200 p-3 text-xs">
          <p className="font-medium text-slate-700">Inbound webhook (for a Zap/scenario to call):</p>
          <p className="mt-1 break-all font-mono text-slate-600">
            {inboundUrl ?? "Configured — reveal the URL by saving again."}
          </p>
          <p className="mt-2 font-medium text-slate-700">Signing secret:</p>
          {revealedSecret ? (
            <p className="mt-1 break-all font-mono text-slate-600">{revealedSecret}</p>
          ) : (
            <p className="mt-1 text-slate-400">
              Shown only once, when generated. Regenerate to get a new one.
            </p>
          )}
          <Button variant="secondary" onClick={() => void regenerate()} disabled={busy} className="mt-2">
            Regenerate secret
          </Button>
          <p className="mt-2 text-slate-400">
            Sign each request with HMAC-SHA256 over{" "}
            <code>{"{timestamp}.{raw body}"}</code>, sent as{" "}
            <code>X-Signature</code> and <code>X-Timestamp</code> headers.
          </p>
        </div>
      ) : null}
      {error ? <p className="mt-2 text-xs text-red-600">{error}</p> : null}
    </Card>
  );
}

// ---------------------------------------------------------------------------
// Page
// ---------------------------------------------------------------------------

export default function ConnectedAppsPage() {
  const { user } = useAuth();
  const { selectedBrandId } = useBrand();
  const isAdmin = user?.role === "admin" || user?.role === "owner";

  const [creds, setCreds] = useState<IntegrationCredential[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    try {
      setCreds(await api.list());
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Failed to load");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  return (
    <>
      <PageHeader
        title="Connected Apps"
        description="Bring your own API keys for low-cost tools. Stored encrypted, scoped to your account."
      />

      {error ? (
        <div className="mb-4 rounded-lg bg-red-50 px-3 py-2 text-sm text-red-700">{error}</div>
      ) : null}

      {loading ? (
        <Spinner />
      ) : !isAdmin ? (
        <Card>
          <p className="text-sm text-slate-500">
            Only account admins and owners can manage connected apps.
          </p>
        </Card>
      ) : (
        <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
          <CalendlyCard cred={findCred(creds, "calendly")} onSaved={load} onRemoved={load} />
          <NotionCard cred={findCred(creds, "notion")} brandId={selectedBrandId} onSaved={load} onRemoved={load} />
          <BitlyCard cred={findCred(creds, "bitly")} onSaved={load} onRemoved={load} />
          <GoogleSheetsCard cred={findCred(creds, "google_sheets")} brandId={selectedBrandId} onSaved={load} onRemoved={load} />
          <ZapierCard cred={findCred(creds, "zapier")} onSaved={load} />
        </div>
      )}
    </>
  );
}
