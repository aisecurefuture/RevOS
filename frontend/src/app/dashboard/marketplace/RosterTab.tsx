"use client";

import { useCallback, useEffect, useState } from "react";

import { Button } from "@/components/ui/Button";
import { Card } from "@/components/ui/Card";
import { Spinner } from "@/components/ui/Spinner";
import { ApiError } from "@/lib/api";
import { INDUSTRIES } from "@/lib/industries";
import { brandsApi, marketplaceApi, offersApi } from "@/lib/resources";
import type { Brand, MatchCreator, MatchProduct, Offer } from "@/lib/types";

type Kind = "creators" | "products";

function Toggle({ checked, onChange, disabled }: { checked: boolean; onChange: () => void; disabled?: boolean }) {
  return (
    <button
      type="button"
      role="switch"
      aria-checked={checked}
      disabled={disabled}
      onClick={onChange}
      className={`relative h-5 w-9 shrink-0 rounded-full transition-colors disabled:opacity-50 ${
        checked ? "bg-brand" : "bg-slate-300"
      }`}
    >
      <span
        className={`absolute top-0.5 h-4 w-4 rounded-full bg-white transition-transform ${
          checked ? "translate-x-4" : "translate-x-0.5"
        }`}
      />
    </button>
  );
}

export function RosterTab({ setNotice }: { setNotice: (s: string | null) => void }) {
  const [kind, setKind] = useState<Kind>("creators");
  const [creators, setCreators] = useState<MatchCreator[]>([]);
  const [products, setProducts] = useState<MatchProduct[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [showAdd, setShowAdd] = useState(false);
  const [togglingId, setTogglingId] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const [c, p] = await Promise.all([
        marketplaceApi.myCreators({ limit: "100" }),
        marketplaceApi.myProducts({ limit: "100" }),
      ]);
      setCreators(c);
      setProducts(p);
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Failed to load your roster");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  async function toggleCreator(c: MatchCreator) {
    setTogglingId(c.id);
    try {
      await marketplaceApi.updateCreator(c.id, { discoverable: !c.discoverable });
      await load();
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Failed to update");
    } finally {
      setTogglingId(null);
    }
  }

  async function toggleProduct(p: MatchProduct) {
    setTogglingId(p.id);
    try {
      await marketplaceApi.updateProduct(p.id, { discoverable: !p.discoverable });
      await load();
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Failed to update");
    } finally {
      setTogglingId(null);
    }
  }

  const items = kind === "creators" ? creators : products;

  return (
    <>
      {error ? (
        <div className="mb-4 rounded-lg bg-red-50 px-3 py-2 text-sm text-red-700">{error}</div>
      ) : null}

      <div className="mb-4 flex items-center justify-between gap-3">
        <div className="flex gap-2">
          {(["creators", "products"] as Kind[]).map((k) => (
            <button
              key={k}
              type="button"
              onClick={() => setKind(k)}
              className={`rounded-lg px-3 py-1.5 text-sm font-medium capitalize ${
                kind === k ? "bg-brand text-white" : "border border-slate-200 bg-white text-slate-600"
              }`}
            >
              {k === "creators" ? "Your creators" : "Your products"}
            </button>
          ))}
        </div>
        <Button onClick={() => setShowAdd(true)}>
          {kind === "creators" ? "Add creator" : "Add product"}
        </Button>
      </div>

      <p className="mb-4 text-xs text-slate-500">
        Turn on <span className="font-medium">Discoverable</span> so brands (or creators) outside your
        workspace can find and request to work with this profile. Off by default — nothing is visible
        in the marketplace until you opt in.
      </p>

      {loading ? (
        <Spinner />
      ) : items.length === 0 ? (
        <Card>
          <p className="text-sm text-slate-400">
            {kind === "creators" ? "No creators yet." : "No products yet."} Add one to start matching.
          </p>
        </Card>
      ) : kind === "creators" ? (
        <div className="space-y-2">
          {creators.map((c) => (
            <Card key={c.id} className="flex items-center justify-between gap-3 py-3">
              <div>
                <p className="text-sm font-medium text-slate-800">{c.display_name}</p>
                <p className="text-xs text-slate-500">
                  {c.handle ?? "—"} · {c.industry?.replace(/_/g, " ") ?? "no industry"}
                  {c.size_tier ? ` · ${c.size_tier}` : ""}
                </p>
              </div>
              <div className="flex items-center gap-2">
                <span className="text-xs text-slate-400">Discoverable</span>
                <Toggle
                  checked={c.discoverable}
                  disabled={togglingId === c.id}
                  onChange={() => void toggleCreator(c)}
                />
              </div>
            </Card>
          ))}
        </div>
      ) : (
        <div className="space-y-2">
          {products.map((p) => (
            <Card key={p.id} className="flex items-center justify-between gap-3 py-3">
              <div>
                <p className="text-sm font-medium text-slate-800">{p.name}</p>
                <p className="text-xs text-slate-500">
                  {p.industry?.replace(/_/g, " ") ?? "no industry"} · {p.status}
                </p>
              </div>
              <div className="flex items-center gap-2">
                <span className="text-xs text-slate-400">Discoverable</span>
                <Toggle
                  checked={p.discoverable}
                  disabled={togglingId === p.id}
                  onChange={() => void toggleProduct(p)}
                />
              </div>
            </Card>
          ))}
        </div>
      )}

      {showAdd ? (
        <AddModal
          kind={kind}
          onClose={() => setShowAdd(false)}
          onCreated={() => {
            setNotice(kind === "creators" ? "Creator added." : "Product added.");
            void load();
          }}
        />
      ) : null}
    </>
  );
}

const INPUT =
  "w-full rounded-lg border border-slate-300 px-3 py-2 text-sm focus:border-brand focus:outline-none focus:ring-1 focus:ring-brand";
const LABEL = "mb-1 block text-xs font-medium text-slate-500";

type ProductSource = "new" | "offer";

function AddModal({
  kind, onClose, onCreated,
}: { kind: Kind; onClose: () => void; onCreated: () => void }) {
  const [name, setName] = useState("");
  const [handle, setHandle] = useState("");
  const [industry, setIndustry] = useState("");
  const [followers, setFollowers] = useState("");
  const [description, setDescription] = useState("");
  const [discoverable, setDiscoverable] = useState(false);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Reuse: link an existing Brand (its Brand Book carries over — no re-entry).
  const [brands, setBrands] = useState<Brand[]>([]);
  const [brandId, setBrandId] = useState("");

  // Products only: seed from an existing Offer instead of starting blank.
  const [source, setSource] = useState<ProductSource>("new");
  const [offers, setOffers] = useState<Offer[]>([]);
  const [offerId, setOfferId] = useState("");

  useEffect(() => {
    void brandsApi.list().then(setBrands).catch(() => setBrands([]));
    if (kind === "products") {
      void offersApi.list().then(setOffers).catch(() => setOffers([]));
    }
  }, [kind]);

  const importingOffer = kind === "products" && source === "offer";
  const canSave = importingOffer
    ? !!offerId && !saving
    : name.trim().length > 0 && !saving;

  async function save(e: React.FormEvent) {
    e.preventDefault();
    if (!canSave) return;
    setSaving(true);
    setError(null);
    try {
      if (kind === "creators") {
        await marketplaceApi.createCreator({
          display_name: name.trim(),
          handle: handle.trim() || undefined,
          industry: industry || undefined,
          follower_count: followers ? Number(followers) : undefined,
          brand_id: brandId || undefined,
          discoverable,
        });
      } else if (importingOffer) {
        await marketplaceApi.importOfferProduct({
          offer_id: offerId,
          industry: industry || undefined,
          status: "active",
          discoverable,
        });
      } else {
        await marketplaceApi.createProduct({
          name: name.trim(),
          industry: industry || undefined,
          description: description.trim() || undefined,
          brand_id: brandId || undefined,
          status: "active",
          discoverable,
        });
      }
      onCreated();
      onClose();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Failed to save");
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className="fixed inset-0 z-50 flex items-start justify-center overflow-y-auto bg-black/40 p-4 sm:p-8" onClick={onClose}>
      <div className="w-full max-w-md rounded-xl bg-white p-6 shadow-xl" onClick={(e) => e.stopPropagation()}>
        <h2 className="mb-4 text-lg font-semibold text-slate-800">
          {kind === "creators" ? "Add a creator" : "Add a product"}
        </h2>
        {error ? <div className="mb-3 rounded-lg bg-red-50 px-3 py-2 text-sm text-red-700">{error}</div> : null}

        {kind === "products" ? (
          <div className="mb-3 flex gap-2">
            <button
              type="button"
              onClick={() => setSource("new")}
              className={`rounded-lg px-3 py-1.5 text-xs font-medium ${
                source === "new" ? "bg-brand text-white" : "border border-slate-200 bg-white text-slate-600"
              }`}
            >
              New product
            </button>
            <button
              type="button"
              onClick={() => setSource("offer")}
              className={`rounded-lg px-3 py-1.5 text-xs font-medium ${
                source === "offer" ? "bg-brand text-white" : "border border-slate-200 bg-white text-slate-600"
              }`}
            >
              Import from an offer
            </button>
          </div>
        ) : null}

        <form onSubmit={save} className="space-y-3">
          {importingOffer ? (
            <div>
              <label className={LABEL}>Offer *</label>
              <select value={offerId} onChange={(e) => setOfferId(e.target.value)} className={INPUT} required>
                <option value="">Select an offer…</option>
                {offers.map((o) => (
                  <option key={o.id} value={o.id}>{o.name}</option>
                ))}
              </select>
              <p className="mt-1 text-xs text-slate-400">
                Name, description, and brand carry over from the offer — no need to retype them.
              </p>
              {offers.length === 0 ? (
                <p className="mt-1 text-xs text-amber-600">
                  No offers found. Create one under Offers first, or add a new product instead.
                </p>
              ) : null}
            </div>
          ) : (
            <>
              <div>
                <label className={LABEL}>{kind === "creators" ? "Display name *" : "Product name *"}</label>
                <input value={name} onChange={(e) => setName(e.target.value)} className={INPUT} required />
              </div>
              {kind === "creators" ? (
                <div className="grid grid-cols-2 gap-3">
                  <div>
                    <label className={LABEL}>Handle</label>
                    <input value={handle} onChange={(e) => setHandle(e.target.value)} placeholder="@handle" className={INPUT} />
                  </div>
                  <div>
                    <label className={LABEL}>Followers</label>
                    <input
                      type="number"
                      min={0}
                      value={followers}
                      onChange={(e) => setFollowers(e.target.value)}
                      className={INPUT}
                    />
                  </div>
                </div>
              ) : (
                <div>
                  <label className={LABEL}>Description</label>
                  <textarea value={description} onChange={(e) => setDescription(e.target.value)} rows={3} className={INPUT} />
                </div>
              )}
              <div>
                <label className={LABEL}>
                  Link a brand <span className="font-normal text-slate-400">(optional — reuses its Brand Book)</span>
                </label>
                <select value={brandId} onChange={(e) => setBrandId(e.target.value)} className={INPUT}>
                  <option value="">None</option>
                  {brands.map((b) => (
                    <option key={b.id} value={b.id}>{b.name}</option>
                  ))}
                </select>
                {brands.length === 0 ? (
                  <p className="mt-1 text-xs text-slate-400">
                    Already done your brand book? Create the brand first and link it here — no need to redo it.
                  </p>
                ) : null}
              </div>
            </>
          )}
          <div>
            <label className={LABEL}>Industry</label>
            <select value={industry} onChange={(e) => setIndustry(e.target.value)} className={INPUT}>
              <option value="">None</option>
              {INDUSTRIES.map((i) => (
                <option key={i.value} value={i.value}>{i.label}</option>
              ))}
            </select>
          </div>
          <label className="flex items-center gap-2 text-sm text-slate-700">
            <input
              type="checkbox"
              checked={discoverable}
              onChange={(e) => setDiscoverable(e.target.checked)}
            />
            Make discoverable in the marketplace right away
          </label>
          <div className="flex justify-end gap-2 pt-1">
            <Button type="button" variant="secondary" onClick={onClose}>Cancel</Button>
            <Button type="submit" disabled={!canSave}>{saving ? "Saving…" : "Add"}</Button>
          </div>
        </form>
      </div>
    </div>
  );
}
