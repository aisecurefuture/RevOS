"use client";

import { useCallback, useEffect, useState } from "react";

import { ApiError, publicSchedulerApi } from "@/lib/api";

const BROWSER_TZ = Intl.DateTimeFormat().resolvedOptions().timeZone || "UTC";

function isoDate(d: Date): string {
  return d.toISOString().slice(0, 10);
}

function nextDays(n: number): Date[] {
  const out: Date[] = [];
  const base = new Date();
  for (let i = 0; i < n; i++) {
    const d = new Date(base);
    d.setDate(base.getDate() + i);
    out.push(d);
  }
  return out;
}

/**
 * Renders a date strip + open-slot buttons for an event type. Slots come from
 * the API as naive-UTC strings; we append "Z" so the browser renders them in
 * the invitee's local timezone.
 */
export function SchedulerSlotPicker({
  eventTypeId,
  onSelect,
}: {
  eventTypeId: string;
  onSelect: (isoSlotUtc: string) => void;
}) {
  const days = nextDays(14);
  const [selectedDate, setSelectedDate] = useState<string>(isoDate(days[0]));
  const [slots, setSlots] = useState<string[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const loadSlots = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const r = await publicSchedulerApi.getSlots(eventTypeId, selectedDate, selectedDate);
      setSlots(r.slots);
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Could not load times");
    } finally {
      setLoading(false);
    }
  }, [eventTypeId, selectedDate]);

  useEffect(() => {
    void loadSlots();
  }, [loadSlots]);

  return (
    <div>
      <p className="mb-2 text-xs text-slate-400">Times shown in your timezone ({BROWSER_TZ})</p>
      <div className="mb-4 flex gap-1 overflow-x-auto pb-1">
        {days.map((d) => {
          const iso = isoDate(d);
          const active = iso === selectedDate;
          return (
            <button
              key={iso}
              onClick={() => setSelectedDate(iso)}
              className={`shrink-0 rounded-lg border px-3 py-2 text-center text-xs ${
                active
                  ? "border-brand bg-brand/5 text-brand"
                  : "border-slate-200 text-slate-600 hover:border-slate-300"
              }`}
            >
              <div className="font-medium">
                {d.toLocaleDateString(undefined, { weekday: "short" })}
              </div>
              <div>{d.toLocaleDateString(undefined, { month: "short", day: "numeric" })}</div>
            </button>
          );
        })}
      </div>

      {loading ? (
        <p className="text-sm text-slate-400">Loading times…</p>
      ) : error ? (
        <p className="text-sm text-red-600">{error}</p>
      ) : slots.length === 0 ? (
        <p className="text-sm text-slate-400">No open times on this day. Try another date.</p>
      ) : (
        <div className="grid grid-cols-3 gap-2 sm:grid-cols-4">
          {slots.map((s) => (
            <button
              key={s}
              onClick={() => onSelect(s)}
              className="rounded-lg border border-slate-200 px-2 py-2 text-sm text-slate-700 hover:border-brand hover:bg-brand/5"
            >
              {new Date(s + "Z").toLocaleTimeString(undefined, { hour: "numeric", minute: "2-digit" })}
            </button>
          ))}
        </div>
      )}
    </div>
  );
}

export { BROWSER_TZ };
