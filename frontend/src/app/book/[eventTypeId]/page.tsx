"use client";

import { use, useEffect, useState } from "react";

import { Button } from "@/components/ui/Button";
import { BROWSER_TZ, SchedulerSlotPicker } from "@/components/SchedulerSlotPicker";
import { ApiError, publicSchedulerApi, type PublicBooking, type PublicEventType } from "@/lib/api";

function fmtSlot(iso: string) {
  return new Date(iso + "Z").toLocaleString(undefined, {
    weekday: "long", month: "long", day: "numeric",
    hour: "numeric", minute: "2-digit",
  });
}

export default function BookPage({ params }: { params: Promise<{ eventTypeId: string }> }) {
  const { eventTypeId } = use(params);

  const [event, setEvent] = useState<PublicEventType | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [slot, setSlot] = useState<string | null>(null);
  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [notes, setNotes] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [confirmed, setConfirmed] = useState<PublicBooking | null>(null);

  useEffect(() => {
    publicSchedulerApi
      .getEvent(eventTypeId)
      .then(setEvent)
      .catch((e) => setLoadError(e instanceof ApiError ? e.message : "This link is not available."));
  }, [eventTypeId]);

  async function book(e: React.FormEvent) {
    e.preventDefault();
    if (!slot) return;
    setBusy(true);
    setError(null);
    try {
      const b = await publicSchedulerApi.book(eventTypeId, {
        start_at: slot,
        invitee_name: name,
        invitee_email: email,
        invitee_timezone: BROWSER_TZ,
        invitee_notes: notes || undefined,
      });
      setConfirmed(b);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not book that time.");
      if (err instanceof ApiError && err.status === 409) {
        // Slot was taken while filling the form — send them back to pick again.
        setSlot(null);
      }
    } finally {
      setBusy(false);
    }
  }

  const shell = (children: React.ReactNode) => (
    <div className="min-h-screen bg-slate-50 px-4 py-10">
      <div className="mx-auto max-w-lg rounded-2xl border border-slate-200 bg-white p-6 shadow-sm">
        {children}
      </div>
    </div>
  );

  if (loadError) return shell(<p className="text-center text-slate-500">{loadError}</p>);
  if (!event) return shell(<p className="text-center text-slate-400">Loading…</p>);

  if (confirmed) {
    const manageUrl = `${typeof window !== "undefined" ? window.location.origin : ""}/booking/${confirmed.manage_token}`;
    return shell(
      <div className="text-center">
        <div className="mb-3 text-4xl">✓</div>
        <h1 className="text-xl font-bold text-slate-900">You&apos;re booked</h1>
        <p className="mt-2 text-slate-600">{event.name}</p>
        <p className="mt-1 font-medium text-slate-800">{fmtSlot(confirmed.start_at)}</p>
        {confirmed.location_detail ? (
          <p className="mt-2 text-sm text-slate-500">Location: {confirmed.location_detail}</p>
        ) : null}
        <p className="mt-4 text-sm text-slate-500">
          A confirmation was emailed to {confirmed.invitee_email}.
        </p>
        <a href={manageUrl} className="mt-4 inline-block text-sm text-brand underline">
          Reschedule or cancel
        </a>
      </div>,
    );
  }

  return shell(
    <>
      <h1 className="text-xl font-bold text-slate-900">{event.name}</h1>
      <p className="mt-1 text-sm text-slate-500">{event.duration_minutes} minutes</p>
      {event.description ? <p className="mt-2 text-sm text-slate-600">{event.description}</p> : null}

      <div className="mt-5">
        {!slot ? (
          <SchedulerSlotPicker eventTypeId={eventTypeId} onSelect={setSlot} />
        ) : (
          <form onSubmit={book} className="space-y-3">
            <div className="rounded-lg bg-brand/5 border border-brand/20 px-3 py-2 text-sm text-slate-700">
              {fmtSlot(slot)}
              <button
                type="button" onClick={() => setSlot(null)}
                className="ml-2 text-xs text-brand underline"
              >
                change
              </button>
            </div>
            <input
              required value={name} onChange={(e) => setName(e.target.value)}
              placeholder="Your name"
              className="w-full rounded-lg border border-slate-300 px-3 py-2 text-sm"
            />
            <input
              required type="email" value={email} onChange={(e) => setEmail(e.target.value)}
              placeholder="Your email"
              className="w-full rounded-lg border border-slate-300 px-3 py-2 text-sm"
            />
            <textarea
              value={notes} onChange={(e) => setNotes(e.target.value)}
              placeholder="Anything to share before the meeting? (optional)"
              rows={3}
              className="w-full rounded-lg border border-slate-300 px-3 py-2 text-sm"
            />
            {error ? <p className="text-sm text-red-600">{error}</p> : null}
            <Button type="submit" disabled={busy} className="w-full">
              {busy ? "Booking…" : "Confirm booking"}
            </Button>
          </form>
        )}
      </div>
    </>,
  );
}
