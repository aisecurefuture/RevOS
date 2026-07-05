"use client";

import { use, useEffect, useState } from "react";

import { Button } from "@/components/ui/Button";
import { SchedulerSlotPicker } from "@/components/SchedulerSlotPicker";
import { ApiError, publicSchedulerApi, type PublicBooking } from "@/lib/api";

function fmtSlot(iso: string) {
  return new Date(iso + "Z").toLocaleString(undefined, {
    weekday: "long", month: "long", day: "numeric",
    hour: "numeric", minute: "2-digit",
  });
}

export default function ManageBookingPage({ params }: { params: Promise<{ token: string }> }) {
  const { token } = use(params);

  const [booking, setBooking] = useState<PublicBooking | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [rescheduling, setRescheduling] = useState(false);

  useEffect(() => {
    publicSchedulerApi
      .getBooking(token)
      .then(setBooking)
      .catch((e) => setLoadError(e instanceof ApiError ? e.message : "Booking not found."));
  }, [token]);

  async function cancel() {
    if (!confirm("Cancel this booking?")) return;
    setBusy(true);
    setError(null);
    try {
      setBooking(await publicSchedulerApi.cancel(token));
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Could not cancel.");
    } finally {
      setBusy(false);
    }
  }

  async function reschedule(slot: string) {
    setBusy(true);
    setError(null);
    try {
      const b = await publicSchedulerApi.reschedule(token, slot);
      setBooking(b);
      setRescheduling(false);
      // The reschedule mints a fresh manage token; move the user to it.
      if (typeof window !== "undefined") {
        window.history.replaceState(null, "", `/booking/${b.manage_token}`);
      }
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Could not reschedule.");
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
  if (!booking) return shell(<p className="text-center text-slate-400">Loading…</p>);

  if (booking.status === "cancelled") {
    return shell(
      <div className="text-center">
        <h1 className="text-lg font-bold text-slate-900">Booking cancelled</h1>
        <p className="mt-2 text-sm text-slate-500">This meeting has been cancelled.</p>
      </div>,
    );
  }

  return shell(
    <>
      <h1 className="text-xl font-bold text-slate-900">Your booking</h1>
      <p className="mt-2 font-medium text-slate-800">{fmtSlot(booking.start_at)}</p>
      {booking.location_detail ? (
        <p className="mt-1 text-sm text-slate-500">Location: {booking.location_detail}</p>
      ) : null}
      <p className="mt-1 text-sm text-slate-400">Booked as {booking.invitee_email}</p>

      {error ? <p className="mt-3 text-sm text-red-600">{error}</p> : null}

      {rescheduling ? (
        <div className="mt-5">
          <p className="mb-2 text-sm font-medium text-slate-700">Pick a new time</p>
          <SchedulerSlotPicker eventTypeId={booking.event_type_id} onSelect={(s) => void reschedule(s)} />
          <button
            onClick={() => setRescheduling(false)}
            className="mt-3 text-xs text-slate-400 hover:text-slate-600"
          >
            ← Back
          </button>
        </div>
      ) : (
        <div className="mt-5 flex gap-2">
          <Button variant="secondary" onClick={() => setRescheduling(true)} disabled={busy}>
            Reschedule
          </Button>
          <Button variant="danger" onClick={() => void cancel()} disabled={busy}>
            Cancel booking
          </Button>
        </div>
      )}
    </>,
  );
}
