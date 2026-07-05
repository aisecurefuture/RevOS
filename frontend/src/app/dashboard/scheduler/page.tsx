"use client";

import { useCallback, useEffect, useState } from "react";

import { PageHeader } from "@/components/PageHeader";
import { Button } from "@/components/ui/Button";
import { Card, CardTitle } from "@/components/ui/Card";
import { Spinner } from "@/components/ui/Spinner";
import {
  ApiError,
  schedulerApi,
  type AvailabilityWindow,
  type EventType,
  type SchedulerBooking,
} from "@/lib/api";
import { useAuth } from "@/lib/auth";

const WEEKDAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"];
const BROWSER_TZ = Intl.DateTimeFormat().resolvedOptions().timeZone || "UTC";

interface DayState {
  enabled: boolean;
  start: string;
  end: string;
}

function defaultDays(): DayState[] {
  // Mon–Fri 9–5 on by default.
  return WEEKDAYS.map((_, i) => ({ enabled: i < 5, start: "09:00", end: "17:00" }));
}

function CreateForm({ onCreated }: { onCreated: () => void }) {
  const [name, setName] = useState("");
  const [slug, setSlug] = useState("");
  const [duration, setDuration] = useState(30);
  const [tz, setTz] = useState(BROWSER_TZ);
  const [locationType, setLocationType] = useState<"custom" | "phone" | "in_person">("custom");
  const [locationDetail, setLocationDetail] = useState("");
  const [days, setDays] = useState<DayState[]>(defaultDays());
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  function setDay(i: number, patch: Partial<DayState>) {
    setDays((d) => d.map((day, idx) => (idx === i ? { ...day, ...patch } : day)));
  }

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    const weekly_availability: AvailabilityWindow[] = days
      .map((d, i) => ({ weekday: i, start: d.start, end: d.end, enabled: d.enabled }))
      .filter((d) => d.enabled)
      .map(({ weekday, start, end }) => ({ weekday, start, end }));
    try {
      await schedulerApi.createEventType({
        name,
        slug: slug || name.toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-|-$/g, ""),
        duration_minutes: duration,
        timezone: tz,
        weekly_availability,
        location_type: locationType,
        location_detail: locationDetail || null,
      });
      setName("");
      setSlug("");
      setLocationDetail("");
      setDays(defaultDays());
      onCreated();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not create event type");
    } finally {
      setBusy(false);
    }
  }

  return (
    <Card className="mb-6">
      <CardTitle>New event type</CardTitle>
      <form onSubmit={submit} className="space-y-3">
        <div className="grid grid-cols-1 gap-2 sm:grid-cols-3">
          <input
            required value={name} onChange={(e) => setName(e.target.value)}
            placeholder="Name (e.g. Intro call)"
            className="rounded-lg border border-slate-300 px-3 py-2 text-sm sm:col-span-2"
          />
          <select
            value={duration} onChange={(e) => setDuration(Number(e.target.value))}
            className="rounded-lg border border-slate-300 px-3 py-2 text-sm"
          >
            {[15, 30, 45, 60, 90].map((m) => (
              <option key={m} value={m}>{m} min</option>
            ))}
          </select>
        </div>

        <div className="grid grid-cols-1 gap-2 sm:grid-cols-2">
          <input
            value={tz} onChange={(e) => setTz(e.target.value)}
            placeholder="Timezone (IANA, e.g. America/Chicago)"
            className="rounded-lg border border-slate-300 px-3 py-2 text-sm"
          />
          <div className="flex gap-2">
            <select
              value={locationType}
              onChange={(e) => setLocationType(e.target.value as typeof locationType)}
              className="rounded-lg border border-slate-300 px-3 py-2 text-sm"
            >
              <option value="custom">Video / link</option>
              <option value="phone">Phone</option>
              <option value="in_person">In person</option>
            </select>
            <input
              value={locationDetail} onChange={(e) => setLocationDetail(e.target.value)}
              placeholder="Link / number / address"
              className="grow rounded-lg border border-slate-300 px-3 py-2 text-sm"
            />
          </div>
        </div>

        <div className="rounded-lg border border-slate-200 p-3">
          <p className="mb-2 text-xs font-medium text-slate-500">Weekly availability</p>
          <div className="space-y-1">
            {WEEKDAYS.map((label, i) => (
              <div key={label} className="flex items-center gap-2 text-sm">
                <label className="flex w-16 items-center gap-1">
                  <input
                    type="checkbox" checked={days[i].enabled}
                    onChange={(e) => setDay(i, { enabled: e.target.checked })}
                  />
                  {label}
                </label>
                <input
                  type="time" value={days[i].start} disabled={!days[i].enabled}
                  onChange={(e) => setDay(i, { start: e.target.value })}
                  className="rounded border border-slate-300 px-2 py-1 text-xs disabled:opacity-40"
                />
                <span className="text-slate-400">to</span>
                <input
                  type="time" value={days[i].end} disabled={!days[i].enabled}
                  onChange={(e) => setDay(i, { end: e.target.value })}
                  className="rounded border border-slate-300 px-2 py-1 text-xs disabled:opacity-40"
                />
              </div>
            ))}
          </div>
        </div>

        {error ? <p className="text-xs text-red-600">{error}</p> : null}
        <Button type="submit" disabled={busy}>{busy ? "Creating…" : "Create event type"}</Button>
      </form>
    </Card>
  );
}

function EventTypeRow({ et, onDeleted }: { et: EventType; onDeleted: () => void }) {
  const [copied, setCopied] = useState(false);
  const [busy, setBusy] = useState(false);
  const bookingUrl =
    typeof window !== "undefined" ? `${window.location.origin}/book/${et.id}` : `/book/${et.id}`;

  async function copy() {
    await navigator.clipboard.writeText(bookingUrl);
    setCopied(true);
    setTimeout(() => setCopied(false), 1500);
  }

  async function remove() {
    if (!confirm(`Delete "${et.name}"? Its booking link will stop working.`)) return;
    setBusy(true);
    try {
      await schedulerApi.deleteEventType(et.id);
      onDeleted();
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="flex flex-wrap items-center justify-between gap-2 border-b border-slate-100 py-3 last:border-0">
      <div>
        <p className="font-medium text-slate-800">
          {et.name}
          <span className="ml-2 text-xs text-slate-400">
            {et.duration_minutes} min · {et.timezone}
          </span>
        </p>
        <p className="break-all text-xs text-slate-400">{bookingUrl}</p>
      </div>
      <div className="flex items-center gap-2">
        <Button variant="secondary" onClick={() => void copy()}>
          {copied ? "Copied!" : "Copy link"}
        </Button>
        <button
          onClick={() => void remove()} disabled={busy}
          className="text-xs text-slate-400 hover:text-red-600"
        >
          Delete
        </button>
      </div>
    </div>
  );
}

export default function SchedulerPage() {
  const { user } = useAuth();
  const isAdmin = user?.role === "admin" || user?.role === "owner";

  const [eventTypes, setEventTypes] = useState<EventType[]>([]);
  const [bookings, setBookings] = useState<SchedulerBooking[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    try {
      const [ets, bks] = await Promise.all([
        schedulerApi.listEventTypes(),
        schedulerApi.listBookings(true),
      ]);
      setEventTypes(ets);
      setBookings(bks);
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Failed to load scheduler");
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
        title="Scheduler"
        description="Your own booking pages — invitees pick an open slot, no Calendly needed."
      />

      {error ? (
        <div className="mb-4 rounded-lg bg-red-50 px-3 py-2 text-sm text-red-700">{error}</div>
      ) : null}

      {loading ? (
        <Spinner />
      ) : (
        <>
          {isAdmin ? <CreateForm onCreated={load} /> : null}

          <Card className="mb-6">
            <CardTitle>Event types</CardTitle>
            {eventTypes.length === 0 ? (
              <p className="text-sm text-slate-400">No event types yet.</p>
            ) : (
              eventTypes.map((et) => <EventTypeRow key={et.id} et={et} onDeleted={load} />)
            )}
          </Card>

          <Card>
            <CardTitle>Upcoming bookings</CardTitle>
            {bookings.length === 0 ? (
              <p className="text-sm text-slate-400">No upcoming bookings.</p>
            ) : (
              <ul className="divide-y divide-slate-100">
                {bookings.map((b) => (
                  <li key={b.id} className="flex items-center justify-between py-2 text-sm">
                    <span className="text-slate-700">
                      {b.invitee_name}{" "}
                      <span className="text-xs text-slate-400">({b.invitee_email})</span>
                    </span>
                    <span className="text-xs text-slate-500">
                      {new Date(b.start_at + "Z").toLocaleString()}
                    </span>
                  </li>
                ))}
              </ul>
            )}
          </Card>
        </>
      )}
    </>
  );
}
