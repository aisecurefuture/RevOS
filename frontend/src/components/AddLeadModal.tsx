"use client";

import { useState } from "react";

import { type Channel, ContactChannelRows } from "@/components/ContactChannelRows";
import { Button } from "@/components/ui/Button";
import { ApiError } from "@/lib/api";
import { leadsApi } from "@/lib/resources";

type Variant = "lead" | "contact";

interface Props {
  open: boolean;
  variant: Variant;
  brandId: string | null; // null = "All Brands"; backend resolves the default brand
  onClose: () => void;
  onCreated: () => void;
}

const INPUT =
  "w-full rounded-lg border border-slate-300 px-3 py-2 text-sm focus:border-brand focus:outline-none focus:ring-1 focus:ring-brand";
const LABEL = "mb-1 block text-xs font-medium text-slate-500";

export function AddLeadModal({ open, variant, brandId, onClose, onCreated }: Props) {
  const isContact = variant === "contact";
  const noun = isContact ? "contact" : "lead";

  const [email, setEmail] = useState("");
  const [firstName, setFirstName] = useState("");
  const [lastName, setLastName] = useState("");
  const [phone, setPhone] = useState("");
  const [company, setCompany] = useState("");
  const [title, setTitle] = useState("");
  const [addEmails, setAddEmails] = useState<Channel[]>([]);
  const [addPhones, setAddPhones] = useState<Channel[]>([]);
  const [notes, setNotes] = useState("");
  const [addr, setAddr] = useState({ line1: "", line2: "", city: "", region: "", postal: "", country: "" });
  const [basis, setBasis] = useState("");
  const [mode, setMode] = useState<"express" | "double_optin">("express");
  const [attested, setAttested] = useState(false);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  if (!open) return null;

  function reset() {
    setEmail(""); setFirstName(""); setLastName(""); setPhone(""); setCompany("");
    setTitle(""); setAddEmails([]); setAddPhones([]); setNotes("");
    setAddr({ line1: "", line2: "", city: "", region: "", postal: "", country: "" });
    setBasis(""); setMode("express"); setAttested(false); setError(null);
  }

  const canSubmit = !!email && attested && basis.trim().length >= 3 && !saving;

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    if (!canSubmit) return;
    setSaving(true);
    setError(null);
    try {
      const cleanChannels = (list: Channel[]) =>
        list.map((c) => ({ value: c.value.trim(), label: c.label.trim() || undefined }))
          .filter((c) => c.value);
      await leadsApi.create({
        brand_id: brandId ?? undefined,
        email,
        first_name: firstName || undefined,
        last_name: lastName || undefined,
        phone: phone || undefined,
        company_name: company || undefined,
        title: isContact ? title || undefined : undefined,
        opt_in_attested: attested,
        consent_basis: basis.trim(),
        consent_mode: mode,
        also_create_contact: isContact,
        source: "manual",
        ...(isContact
          ? {
              additional_emails: cleanChannels(addEmails),
              additional_phones: cleanChannels(addPhones),
              notes: notes.trim() || undefined,
              address_line1: addr.line1 || undefined,
              address_line2: addr.line2 || undefined,
              city: addr.city || undefined,
              region: addr.region || undefined,
              postal_code: addr.postal || undefined,
              country: addr.country || undefined,
            }
          : {}),
      });
      reset();
      onCreated();
      onClose();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : `Failed to add ${noun}`);
    } finally {
      setSaving(false);
    }
  }

  return (
    <div
      className="fixed inset-0 z-50 flex items-start justify-center overflow-y-auto bg-black/40 p-4 sm:p-8"
      onClick={onClose}
    >
      <div
        className="w-full max-w-lg rounded-xl bg-white p-6 shadow-xl"
        onClick={(e) => e.stopPropagation()}
      >
        <h2 className="mb-1 text-lg font-semibold text-slate-800">
          Add {noun} with opt-in attestation
        </h2>
        <p className="mb-4 text-xs text-slate-500">
          Only add people who have opted in to hear from you. Your attestation is stored as
          an immutable consent record.
        </p>

        {error ? (
          <div className="mb-3 rounded-lg bg-red-50 px-3 py-2 text-sm text-red-700">{error}</div>
        ) : null}

        <form onSubmit={submit} className="space-y-3">
          <div>
            <label className={LABEL}>{isContact ? "Primary email *" : "Email *"}</label>
            <input
              type="email"
              required
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              placeholder="name@company.com"
              className={INPUT}
            />
            {isContact ? <ContactChannelRows kind="email" list={addEmails} set={setAddEmails} /> : null}
          </div>

          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className={LABEL}>First name</label>
              <input value={firstName} onChange={(e) => setFirstName(e.target.value)} className={INPUT} />
            </div>
            <div>
              <label className={LABEL}>Last name</label>
              <input value={lastName} onChange={(e) => setLastName(e.target.value)} className={INPUT} />
            </div>
          </div>

          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className={LABEL}>{isContact ? "Primary phone" : "Phone"}</label>
              <input value={phone} onChange={(e) => setPhone(e.target.value)} className={INPUT} />
            </div>
            <div>
              <label className={LABEL}>Company</label>
              <input value={company} onChange={(e) => setCompany(e.target.value)} className={INPUT} />
            </div>
          </div>
          {isContact ? <ContactChannelRows kind="phone" list={addPhones} set={setAddPhones} /> : null}

          {isContact ? (
            <>
              <div>
                <label className={LABEL}>Title</label>
                <input value={title} onChange={(e) => setTitle(e.target.value)} className={INPUT} />
              </div>

              <div>
                <label className={LABEL}>Address</label>
                <div className="space-y-2">
                  <input
                    value={addr.line1}
                    onChange={(e) => setAddr({ ...addr, line1: e.target.value })}
                    placeholder="Street address"
                    className={INPUT}
                  />
                  <input
                    value={addr.line2}
                    onChange={(e) => setAddr({ ...addr, line2: e.target.value })}
                    placeholder="Apt, suite, unit (optional)"
                    className={INPUT}
                  />
                  <div className="grid grid-cols-2 gap-2">
                    <input value={addr.city} onChange={(e) => setAddr({ ...addr, city: e.target.value })} placeholder="City" className={INPUT} />
                    <input value={addr.region} onChange={(e) => setAddr({ ...addr, region: e.target.value })} placeholder="State / region" className={INPUT} />
                  </div>
                  <div className="grid grid-cols-2 gap-2">
                    <input value={addr.postal} onChange={(e) => setAddr({ ...addr, postal: e.target.value })} placeholder="ZIP / postal" className={INPUT} />
                    <input value={addr.country} onChange={(e) => setAddr({ ...addr, country: e.target.value })} placeholder="Country" className={INPUT} />
                  </div>
                </div>
              </div>

              <div>
                <label className={LABEL}>Notes</label>
                <textarea
                  value={notes}
                  onChange={(e) => setNotes(e.target.value)}
                  rows={3}
                  placeholder="Context, preferences, where you met…"
                  className={INPUT}
                />
              </div>
            </>
          ) : null}

          <div className="rounded-lg border border-slate-200 bg-slate-50 p-3">
            <label className="mb-1 block text-xs font-medium text-slate-600">
              How did they opt in? *
            </label>
            <textarea
              value={basis}
              onChange={(e) => setBasis(e.target.value)}
              rows={2}
              placeholder="e.g. Verbal consent at open house on 2026-07-20; business card exchanged"
              className={INPUT}
            />

            <div className="mt-3 space-y-2 text-sm text-slate-700">
              <label className="flex items-start gap-2">
                <input type="radio" name="mode" checked={mode === "express"} onChange={() => setMode("express")} className="mt-0.5" />
                <span>
                  <span className="font-medium">Express consent — mailable now.</span> They gave
                  direct written/verbal permission to receive marketing.
                </span>
              </label>
              <label className="flex items-start gap-2">
                <input type="radio" name="mode" checked={mode === "double_optin"} onChange={() => setMode("double_optin")} className="mt-0.5" />
                <span>
                  <span className="font-medium">Send a confirmation email first.</span> Mailable
                  only after they click the confirm link (double opt-in).
                </span>
              </label>
            </div>

            <label className="mt-3 flex items-start gap-2 text-sm text-slate-700">
              <input type="checkbox" checked={attested} onChange={(e) => setAttested(e.target.checked)} className="mt-0.5" />
              <span>
                I attest that this person opted in to receive communications, as described above. *
              </span>
            </label>
          </div>

          <div className="flex justify-end gap-2 pt-1">
            <Button type="button" variant="secondary" onClick={onClose}>
              Cancel
            </Button>
            <Button type="submit" disabled={!canSubmit}>
              {saving ? "Adding…" : `Add ${noun}`}
            </Button>
          </div>
        </form>
      </div>
    </div>
  );
}
