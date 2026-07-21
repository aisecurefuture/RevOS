"use client";

export type Channel = { value: string; label: string };

const INPUT =
  "w-full rounded-lg border border-slate-300 px-3 py-2 text-sm focus:border-brand focus:outline-none focus:ring-1 focus:ring-brand";

/** Editable list of additional emails or phones (the primary lives in its own
 *  field). Module-level so it isn't re-created each render — otherwise the
 *  inputs would lose focus on every keystroke. */
export function ContactChannelRows({
  kind, list, set,
}: { kind: "email" | "phone"; list: Channel[]; set: (c: Channel[]) => void }) {
  const patch = (i: number, p: Partial<Channel>) =>
    set(list.map((c, idx) => (idx === i ? { ...c, ...p } : c)));
  return (
    <div className="mt-2 space-y-2">
      {list.map((c, i) => (
        <div key={i} className="flex gap-2">
          <input
            type={kind === "email" ? "email" : "tel"}
            value={c.value}
            onChange={(e) => patch(i, { value: e.target.value })}
            placeholder={kind === "email" ? "another@email.com" : "Additional phone"}
            className={INPUT}
          />
          <input
            value={c.label}
            onChange={(e) => patch(i, { label: e.target.value })}
            placeholder={kind === "email" ? "label (work)" : "label (office)"}
            className="w-28 shrink-0 rounded-lg border border-slate-300 px-2 py-2 text-sm focus:border-brand focus:outline-none"
          />
          <button
            type="button"
            onClick={() => set(list.filter((_, idx) => idx !== i))}
            className="shrink-0 px-2 text-slate-400 hover:text-red-600"
            aria-label={`Remove ${kind}`}
          >
            ✕
          </button>
        </div>
      ))}
      <button
        type="button"
        onClick={() => set([...list, { value: "", label: "" }])}
        className="text-xs font-medium text-brand hover:underline"
      >
        + Add another {kind}
      </button>
    </div>
  );
}
