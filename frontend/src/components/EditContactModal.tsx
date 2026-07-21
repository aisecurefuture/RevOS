"use client";

import { useState } from "react";

import { type Channel, ContactChannelRows } from "@/components/ContactChannelRows";
import { Button } from "@/components/ui/Button";
import { ApiError } from "@/lib/api";
import { contactsApi } from "@/lib/resources";
import type { Contact, ContactChannel } from "@/lib/types";

const INPUT =
  "w-full rounded-lg border border-slate-300 px-3 py-2 text-sm focus:border-brand focus:outline-none focus:ring-1 focus:ring-brand";
const LABEL = "mb-1 block text-xs font-medium text-slate-500";

const STAGES = ["subscriber", "lead", "mql", "sql", "opportunity", "customer", "evangelist"];

interface Props {
  contact: Contact;
  onClose: () => void;
  onSaved: () => void;
}

/** Split a contact's stored channel list into its primary value + the rest. */
function splitChannels(list: ContactChannel[] | undefined, scalar: string | null | undefined) {
  const entries = (list ?? []).map((c) => ({ value: c.value, label: c.label ?? "", is_primary: c.is_primary }));
  const primary = entries.find((c) => c.is_primary)?.value ?? scalar ?? "";
  const extras: Channel[] = entries
    .filter((c) => c.value !== primary)
    .map((c) => ({ value: c.value, label: c.label }));
  return { primary, extras };
}

export function EditContactModal({ contact, onClose, onSaved }: Props) {
  const e0 = splitChannels(contact.emails, contact.email);
  const p0 = splitChannels(contact.phones, contact.phone);

  const [firstName, setFirstName] = useState(contact.first_name ?? "");
  const [lastName, setLastName] = useState(contact.last_name ?? "");
  const [email, setEmail] = useState(e0.primary);
  const [phone, setPhone] = useState(p0.primary);
  const [addEmails, setAddEmails] = useState<Channel[]>(e0.extras);
  const [addPhones, setAddPhones] = useState<Channel[]>(p0.extras);
  const [title, setTitle] = useState(contact.title ?? "");
  const [stage, setStage] = useState(contact.lifecycle_stage);
  const [addr, setAddr] = useState({
    line1: contact.address_line1 ?? "", line2: contact.address_line2 ?? "",
    city: contact.city ?? "", region: contact.region ?? "",
    postal: contact.postal_code ?? "", country: contact.country ?? "",
  });
  const [notes, setNotes] = useState(contact.notes ?? "");
  const [saving, setSaving] = useState(false);
  const [confirmDelete, setConfirmDelete] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const name = [contact.first_name, contact.last_name].filter(Boolean).join(" ") || contact.email || "Contact";

  function channels(primary: string, extras: Channel[]) {
    const out: { value: string; label?: string; is_primary: boolean }[] = [];
    if (primary.trim()) out.push({ value: primary.trim(), is_primary: true });
    for (const c of extras) {
      if (c.value.trim()) out.push({ value: c.value.trim(), label: c.label.trim() || undefined, is_primary: false });
    }
    return out;
  }

  async function save(ev: React.FormEvent) {
    ev.preventDefault();
    setSaving(true);
    setError(null);
    try {
      await contactsApi.update(contact.id, {
        first_name: firstName || null,
        last_name: lastName || null,
        email: email || null,
        phone: phone || null,
        emails: channels(email, addEmails),
        phones: channels(phone, addPhones),
        title: title || null,
        lifecycle_stage: stage,
        notes: notes || null,
        address_line1: addr.line1 || null,
        address_line2: addr.line2 || null,
        city: addr.city || null,
        region: addr.region || null,
        postal_code: addr.postal || null,
        country: addr.country || null,
      });
      onSaved();
      onClose();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Failed to save contact");
    } finally {
      setSaving(false);
    }
  }

  async function remove() {
    setSaving(true);
    setError(null);
    try {
      await contactsApi.remove(contact.id);
      onSaved();
      onClose();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Failed to delete contact");
      setSaving(false);
    }
  }

  return (
    <div
      className="fixed inset-0 z-50 flex items-start justify-center overflow-y-auto bg-black/40 p-4 sm:p-8"
      onClick={onClose}
    >
      <div className="w-full max-w-lg rounded-xl bg-white p-6 shadow-xl" onClick={(ev) => ev.stopPropagation()}>
        <div className="mb-1 flex items-baseline justify-between gap-3">
          <h2 className="text-lg font-semibold text-slate-800">{name}</h2>
          <span className="font-mono text-xs text-slate-400">score {contact.lead_score}</span>
        </div>
        <p className="mb-4 text-xs text-slate-500">
          Edit contact details. Changes are saved to your CRM only — this does not re-send anything.
        </p>

        {error ? (
          <div className="mb-3 rounded-lg bg-red-50 px-3 py-2 text-sm text-red-700">{error}</div>
        ) : null}

        <form onSubmit={save} className="space-y-3">
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

          <div>
            <label className={LABEL}>Primary email</label>
            <input type="email" value={email} onChange={(e) => setEmail(e.target.value)} className={INPUT} />
            <ContactChannelRows kind="email" list={addEmails} set={setAddEmails} />
          </div>

          <div>
            <label className={LABEL}>Primary phone</label>
            <input value={phone} onChange={(e) => setPhone(e.target.value)} className={INPUT} />
            <ContactChannelRows kind="phone" list={addPhones} set={setAddPhones} />
          </div>

          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className={LABEL}>Title</label>
              <input value={title} onChange={(e) => setTitle(e.target.value)} className={INPUT} />
            </div>
            <div>
              <label className={LABEL}>Stage</label>
              <select value={stage} onChange={(e) => setStage(e.target.value)} className={INPUT}>
                {STAGES.map((s) => (
                  <option key={s} value={s} className="capitalize">{s}</option>
                ))}
              </select>
            </div>
          </div>

          <div>
            <label className={LABEL}>Address</label>
            <div className="space-y-2">
              <input value={addr.line1} onChange={(e) => setAddr({ ...addr, line1: e.target.value })} placeholder="Street address" className={INPUT} />
              <input value={addr.line2} onChange={(e) => setAddr({ ...addr, line2: e.target.value })} placeholder="Apt, suite, unit (optional)" className={INPUT} />
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
            <textarea value={notes} onChange={(e) => setNotes(e.target.value)} rows={3} className={INPUT} />
          </div>

          <div className="flex items-center justify-between gap-2 pt-1">
            {confirmDelete ? (
              <div className="flex items-center gap-2">
                <span className="text-xs text-slate-500">Delete this contact?</span>
                <Button type="button" variant="danger" onClick={() => void remove()} disabled={saving}>
                  Confirm
                </Button>
                <button type="button" onClick={() => setConfirmDelete(false)} className="text-xs text-slate-400 hover:text-slate-600">
                  Cancel
                </button>
              </div>
            ) : (
              <button type="button" onClick={() => setConfirmDelete(true)} className="text-xs font-medium text-red-600 hover:underline">
                Delete
              </button>
            )}
            <div className="flex gap-2">
              <Button type="button" variant="secondary" onClick={onClose}>Cancel</Button>
              <Button type="submit" disabled={saving}>{saving ? "Saving…" : "Save changes"}</Button>
            </div>
          </div>
        </form>
      </div>
    </div>
  );
}
