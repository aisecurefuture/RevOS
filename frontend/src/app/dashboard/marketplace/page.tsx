"use client";

import { useCallback, useEffect, useState } from "react";

import { PageHeader } from "@/components/PageHeader";
import { Button } from "@/components/ui/Button";
import { Card } from "@/components/ui/Card";
import { Spinner } from "@/components/ui/Spinner";
import { ApiError } from "@/lib/api";
import { INDUSTRIES } from "@/lib/industries";
import { marketplaceApi } from "@/lib/resources";
import type {
  CreatorDiscovery,
  MatchCreator,
  MatchProduct,
  MatchScore,
  ProductDiscovery,
} from "@/lib/types";

type Mode = "creators" | "brands";
const SIZE_TIERS = ["nano", "micro", "mid", "macro", "mega"];

function scoreColor(v: number): string {
  if (v >= 75) return "bg-green-100 text-green-700";
  if (v >= 55) return "bg-blue-100 text-blue-700";
  if (v >= 35) return "bg-amber-100 text-amber-700";
  return "bg-slate-100 text-slate-500";
}

function ScoreBlock({ score }: { score: MatchScore }) {
  return (
    <div className="mt-2 rounded-lg border border-slate-200 bg-slate-50 p-3">
      <div className="mb-2 flex items-center gap-2">
        <span className={`rounded-full px-2 py-0.5 text-sm font-semibold ${scoreColor(score.overall)}`}>
          {Math.round(score.overall)}
        </span>
        <span className="text-xs text-slate-500">
          match · {Math.round(score.coverage * 100)}% data coverage
        </span>
      </div>
      <p className="mb-2 text-xs text-slate-600">{score.rationale}</p>
      <div className="grid grid-cols-2 gap-1.5">
        {score.dimensions.map((d) => (
          <div key={d.key} className="flex items-center justify-between gap-2 text-xs">
            <span className="capitalize text-slate-500">{d.key.replace(/_/g, " ")}</span>
            <span className={d.available ? "font-medium text-slate-700" : "text-slate-400"}>
              {d.available ? Math.round(d.score) : "—"}
            </span>
          </div>
        ))}
      </div>
    </div>
  );
}

export default function MarketplacePage() {
  const [mode, setMode] = useState<Mode>("creators");
  const [industry, setIndustry] = useState("");
  const [sizeTier, setSizeTier] = useState("");
  const [search, setSearch] = useState("");
  const [rankId, setRankId] = useState("");

  const [myProducts, setMyProducts] = useState<MatchProduct[]>([]);
  const [myCreators, setMyCreators] = useState<MatchCreator[]>([]);
  const [creatorResults, setCreatorResults] = useState<CreatorDiscovery[]>([]);
  const [productResults, setProductResults] = useState<ProductDiscovery[]>([]);

  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [requesting, setRequesting] = useState<{ id: string; name: string } | null>(null);

  // Load the account's own roster for the "rank against" + request pickers.
  useEffect(() => {
    void (async () => {
      try {
        const [p, c] = await Promise.all([
          marketplaceApi.myProducts({ limit: "100" }),
          marketplaceApi.myCreators({ limit: "100" }),
        ]);
        setMyProducts(p);
        setMyCreators(c);
      } catch {
        /* non-fatal — pickers just stay empty */
      }
    })();
  }, []);

  const runSearch = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      if (mode === "creators") {
        setCreatorResults(
          await marketplaceApi.discoverCreators({
            industry: industry || undefined,
            size_tier: sizeTier || undefined,
            search: search || undefined,
            rank_product_id: rankId || undefined,
          }),
        );
      } else {
        setProductResults(
          await marketplaceApi.discoverProducts({
            industry: industry || undefined,
            search: search || undefined,
            rank_creator_id: rankId || undefined,
          }),
        );
      }
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Search failed");
    } finally {
      setLoading(false);
    }
  }, [mode, industry, sizeTier, search, rankId]);

  useEffect(() => {
    setRankId("");
    void runSearch();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [mode]);

  function switchMode(m: Mode) {
    if (m === mode) return;
    setMode(m);
    setCreatorResults([]);
    setProductResults([]);
  }

  return (
    <>
      <PageHeader
        title="Marketplace"
        description="Discover the right partners and reach out. Consent-first — only opted-in profiles appear, and contact details stay private until a request is accepted."
      />

      {error ? (
        <div className="mb-4 rounded-lg bg-red-50 px-3 py-2 text-sm text-red-700">{error}</div>
      ) : null}
      {notice ? (
        <div className="mb-4 rounded-lg bg-green-50 px-3 py-2 text-sm text-green-700">{notice}</div>
      ) : null}

      <div className="mb-4 flex gap-2">
        {(["creators", "brands"] as Mode[]).map((m) => (
          <button
            key={m}
            type="button"
            onClick={() => switchMode(m)}
            className={`rounded-lg px-3 py-1.5 text-sm font-medium ${
              mode === m ? "bg-brand text-white" : "border border-slate-200 bg-white text-slate-600"
            }`}
          >
            {m === "creators" ? "Find creators" : "Find brands / products"}
          </button>
        ))}
      </div>

      <Card className="mb-4">
        <div className="flex flex-wrap items-end gap-3">
          <div>
            <label className="mb-1 block text-xs font-medium text-slate-500">Industry</label>
            <select
              value={industry}
              onChange={(e) => setIndustry(e.target.value)}
              className="rounded-lg border border-slate-300 px-3 py-2 text-sm"
            >
              <option value="">Any industry</option>
              {INDUSTRIES.map((i) => (
                <option key={i.value} value={i.value}>{i.label}</option>
              ))}
            </select>
          </div>
          {mode === "creators" ? (
            <div>
              <label className="mb-1 block text-xs font-medium text-slate-500">Size tier</label>
              <select
                value={sizeTier}
                onChange={(e) => setSizeTier(e.target.value)}
                className="rounded-lg border border-slate-300 px-3 py-2 text-sm capitalize"
              >
                <option value="">Any size</option>
                {SIZE_TIERS.map((t) => (
                  <option key={t} value={t} className="capitalize">{t}</option>
                ))}
              </select>
            </div>
          ) : null}
          <div>
            <label className="mb-1 block text-xs font-medium text-slate-500">
              Rank against {mode === "creators" ? "your product" : "your creator"}
            </label>
            <select
              value={rankId}
              onChange={(e) => setRankId(e.target.value)}
              className="max-w-[13rem] rounded-lg border border-slate-300 px-3 py-2 text-sm"
            >
              <option value="">No ranking</option>
              {(mode === "creators" ? myProducts : myCreators).map((o) => (
                <option key={o.id} value={o.id}>
                  {"name" in o ? (o as MatchProduct).name : (o as MatchCreator).display_name}
                </option>
              ))}
            </select>
          </div>
          <div className="grow">
            <label className="mb-1 block text-xs font-medium text-slate-500">Search</label>
            <input
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              onKeyDown={(e) => e.key === "Enter" && void runSearch()}
              placeholder={mode === "creators" ? "Name or @handle" : "Product name"}
              className="w-full rounded-lg border border-slate-300 px-3 py-2 text-sm"
            />
          </div>
          <Button onClick={() => void runSearch()}>Search</Button>
        </div>
      </Card>

      {loading ? (
        <Spinner />
      ) : mode === "creators" ? (
        <CreatorResults
          results={creatorResults}
          onRequest={(c) => setRequesting({ id: c.id, name: c.display_name })}
        />
      ) : (
        <ProductResults
          results={productResults}
          onRequest={(p) => setRequesting({ id: p.id, name: p.name })}
        />
      )}

      {requesting ? (
        <RequestModal
          mode={mode}
          target={requesting}
          products={myProducts}
          creators={myCreators}
          defaultRankId={rankId}
          onClose={() => setRequesting(null)}
          onSent={() => {
            setNotice(`Request sent to ${requesting.name}.`);
            setRequesting(null);
          }}
        />
      ) : null}
    </>
  );
}

function CreatorResults({
  results, onRequest,
}: { results: CreatorDiscovery[]; onRequest: (c: MatchCreator) => void }) {
  if (results.length === 0) {
    return <Card><p className="text-sm text-slate-400">No discoverable creators match yet.</p></Card>;
  }
  return (
    <div className="grid grid-cols-1 gap-3 lg:grid-cols-2">
      {results.map(({ creator, score }) => (
        <Card key={creator.id}>
          <div className="flex items-start justify-between gap-3">
            <div>
              <p className="font-semibold text-slate-800">{creator.display_name}</p>
              <p className="text-xs text-slate-500">
                {creator.handle ?? "—"} · {creator.industry?.replace(/_/g, " ") ?? "—"}
                {creator.size_tier ? ` · ${creator.size_tier}` : ""}
              </p>
              <p className="mt-1 text-xs text-slate-500">
                {creator.follower_count != null ? `${creator.follower_count.toLocaleString()} followers` : "—"}
                {creator.engagement_rate != null ? ` · ${(creator.engagement_rate * 100).toFixed(1)}% eng.` : ""}
              </p>
            </div>
            <Button variant="secondary" onClick={() => onRequest(creator)}>Request</Button>
          </div>
          {score ? <ScoreBlock score={score} /> : null}
        </Card>
      ))}
    </div>
  );
}

function ProductResults({
  results, onRequest,
}: { results: ProductDiscovery[]; onRequest: (p: MatchProduct) => void }) {
  if (results.length === 0) {
    return <Card><p className="text-sm text-slate-400">No discoverable brands/products match yet.</p></Card>;
  }
  return (
    <div className="grid grid-cols-1 gap-3 lg:grid-cols-2">
      {results.map(({ product, score }) => (
        <Card key={product.id}>
          <div className="flex items-start justify-between gap-3">
            <div>
              <p className="font-semibold text-slate-800">{product.name}</p>
              <p className="text-xs text-slate-500">{product.industry?.replace(/_/g, " ") ?? "—"}</p>
              {product.description ? (
                <p className="mt-1 line-clamp-2 text-xs text-slate-500">{product.description}</p>
              ) : null}
            </div>
            <Button variant="secondary" onClick={() => onRequest(product)}>Request</Button>
          </div>
          {score ? <ScoreBlock score={score} /> : null}
        </Card>
      ))}
    </div>
  );
}

function RequestModal({
  mode, target, products, creators, defaultRankId, onClose, onSent,
}: {
  mode: Mode;
  target: { id: string; name: string };
  products: MatchProduct[];
  creators: MatchCreator[];
  defaultRankId: string;
  onClose: () => void;
  onSent: () => void;
}) {
  // brand→creator: pick which of MY products; creator→brand: pick which of MY creators.
  const [ownId, setOwnId] = useState(defaultRankId);
  const [message, setMessage] = useState("");
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const findingCreators = mode === "creators";
  const ownLabel = findingCreators ? "Which of your products?" : "Send on behalf of which creator?";
  const ownOptions = findingCreators ? products : creators;
  const canSend = !!ownId && message.trim().length > 0 && !saving;

  async function send() {
    if (!canSend) return;
    setSaving(true);
    setError(null);
    try {
      await marketplaceApi.createCollaboration(
        findingCreators
          ? { direction: "brand_to_creator", creator_id: target.id, product_id: ownId, message: message.trim() }
          : { direction: "creator_to_brand", creator_id: ownId, product_id: target.id, message: message.trim() },
      );
      onSent();
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Failed to send request");
      setSaving(false);
    }
  }

  return (
    <div className="fixed inset-0 z-50 flex items-start justify-center overflow-y-auto bg-black/40 p-4 sm:p-8" onClick={onClose}>
      <div className="w-full max-w-md rounded-xl bg-white p-6 shadow-xl" onClick={(e) => e.stopPropagation()}>
        <h2 className="mb-1 text-lg font-semibold text-slate-800">Send a request to {target.name}</h2>
        <p className="mb-4 text-xs text-slate-500">
          One message — they accept or decline. Contact details are shared only if they accept.
        </p>
        {error ? <div className="mb-3 rounded-lg bg-red-50 px-3 py-2 text-sm text-red-700">{error}</div> : null}
        <div className="space-y-3">
          <div>
            <label className="mb-1 block text-xs font-medium text-slate-500">{ownLabel}</label>
            <select value={ownId} onChange={(e) => setOwnId(e.target.value)}
              className="w-full rounded-lg border border-slate-300 px-3 py-2 text-sm">
              <option value="">Select…</option>
              {ownOptions.map((o) => (
                <option key={o.id} value={o.id}>
                  {"name" in o ? (o as MatchProduct).name : (o as MatchCreator).display_name}
                </option>
              ))}
            </select>
          </div>
          <div>
            <label className="mb-1 block text-xs font-medium text-slate-500">Message</label>
            <textarea value={message} onChange={(e) => setMessage(e.target.value)} rows={4}
              placeholder="Introduce the opportunity…"
              className="w-full rounded-lg border border-slate-300 px-3 py-2 text-sm" />
          </div>
          <div className="flex justify-end gap-2">
            <Button type="button" variant="secondary" onClick={onClose}>Cancel</Button>
            <Button type="button" onClick={() => void send()} disabled={!canSend}>
              {saving ? "Sending…" : "Send request"}
            </Button>
          </div>
        </div>
      </div>
    </div>
  );
}
