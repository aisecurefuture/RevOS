"use client";

// Lightweight product tour — a spotlight overlay that walks a new user through
// the key surfaces, skip-at-any-time. No library: steps target elements by a
// `data-tour="key"` attribute; a missing/hidden target is skipped gracefully.
// Completion persists in localStorage (per-browser, consistent with the app's
// other UI state); Help re-runs it regardless of that flag.

import {
  createContext, useCallback, useContext, useLayoutEffect, useMemo, useState,
  type ReactNode,
} from "react";

interface TourStep {
  target: string | null; // data-tour selector; null = centered, no spotlight
  title: string;
  body: string;
}

const STEPS: TourStep[] = [
  {
    target: null,
    title: "Welcome to RevOS360 👋",
    body: "Here's a 60-second tour of how everything fits together. You can skip anytime.",
  },
  {
    target: '[data-tour="nav"]',
    title: "Three simple tiers",
    body: "The app is organized as Define → Reach → Govern: define your brand once, reach people through every channel, and govern everything that goes out.",
  },
  {
    target: '[data-tour="brand-book"]',
    title: "Start with your Brand Book",
    body: "This is your source of truth — voice, claims, and guardrails. Every email, post, and video the platform makes inherits from it.",
  },
  {
    target: '[data-tour="recommended"]',
    title: "Your recommended starting points",
    body: "We've highlighted the features most useful for your industry on the dashboard. Begin with the one marked “Start here”.",
  },
  {
    target: '[data-tour="approvals"]',
    title: "Nothing goes out without you",
    body: "Approval-first is the whole idea: AI drafts, you approve. This is the surface where you review everything before it's published.",
  },
  {
    target: null,
    title: "That's the tour! 🎉",
    body: "Explore at your own pace. You can replay this tour anytime from the Help menu in the sidebar.",
  },
];

const TOUR_KEY = "revos.tourDone";

interface TourState {
  startTour: () => void;
  active: boolean;
}

const TourContext = createContext<TourState | null>(null);

export function hasSeenTour(): boolean {
  if (typeof window === "undefined") return true;
  return window.localStorage.getItem(TOUR_KEY) === "1";
}

export function TourProvider({ children }: { children: ReactNode }) {
  const [active, setActive] = useState(false);
  const [index, setIndex] = useState(0);

  // Explicit start only — from new-user moments (first brand / onboarding
  // skip) and the Help menu. Never auto-runs for established users.
  const startTour = useCallback(() => {
    setIndex(0);
    setActive(true);
  }, []);

  const finish = useCallback(() => {
    setActive(false);
    try {
      window.localStorage.setItem(TOUR_KEY, "1");
    } catch {
      /* private mode — just won't persist */
    }
  }, []);

  // Skip steps whose target isn't on the page (e.g. a feature not yet built,
  // or a role-hidden nav item), in the current direction.
  const resolveStep = useCallback((from: number, dir: 1 | -1): number => {
    let i = from;
    while (i >= 0 && i < STEPS.length) {
      const step = STEPS[i];
      if (!step.target || document.querySelector(step.target)) return i;
      i += dir;
    }
    return -1;
  }, []);

  const go = useCallback((dir: 1 | -1) => {
    setIndex((cur) => {
      const next = resolveStep(cur + dir, dir);
      if (next === -1) {
        finish();
        return cur;
      }
      return next;
    });
  }, [resolveStep, finish]);

  const value = useMemo(() => ({ startTour, active }), [startTour, active]);

  return (
    <TourContext.Provider value={value}>
      {children}
      {active ? (
        <TourOverlay
          step={STEPS[index]}
          index={index}
          total={STEPS.length}
          onNext={() => go(1)}
          onBack={() => go(-1)}
          onSkip={finish}
        />
      ) : null}
    </TourContext.Provider>
  );
}

export function useTour(): TourState {
  const ctx = useContext(TourContext);
  if (!ctx) throw new Error("useTour must be used within a TourProvider");
  return ctx;
}

interface Rect { top: number; left: number; width: number; height: number; }

function TourOverlay({
  step, index, total, onNext, onBack, onSkip,
}: {
  step: TourStep; index: number; total: number;
  onNext: () => void; onBack: () => void; onSkip: () => void;
}) {
  const [rect, setRect] = useState<Rect | null>(null);

  useLayoutEffect(() => {
    if (!step.target) { setRect(null); return; }
    const measure = () => {
      const el = document.querySelector(step.target!);
      if (!el) { setRect(null); return; }
      el.scrollIntoView({ block: "nearest", behavior: "smooth" });
      const r = el.getBoundingClientRect();
      setRect({ top: r.top, left: r.left, width: r.width, height: r.height });
    };
    measure();
    window.addEventListener("resize", measure);
    window.addEventListener("scroll", measure, true);
    return () => {
      window.removeEventListener("resize", measure);
      window.removeEventListener("scroll", measure, true);
    };
  }, [step.target]);

  const pad = 6;
  const spotlight: React.CSSProperties | null = rect
    ? {
        position: "fixed",
        top: rect.top - pad,
        left: rect.left - pad,
        width: rect.width + pad * 2,
        height: rect.height + pad * 2,
        borderRadius: 12,
        boxShadow: "0 0 0 9999px rgba(15,23,42,0.55)",
        outline: "2px solid rgba(99,102,241,0.9)",
        pointerEvents: "none",
        zIndex: 1000,
        transition: "all .2s ease",
      }
    : null;

  // Tooltip placement: below the target if room, else above; centered when
  // there's no target.
  const tipStyle: React.CSSProperties = rect
    ? (() => {
        const below = rect.top + rect.height + 320 < window.innerHeight;
        return {
          position: "fixed",
          top: below ? rect.top + rect.height + 16 : undefined,
          bottom: below ? undefined : window.innerHeight - rect.top + 16,
          left: Math.min(Math.max(rect.left, 16), window.innerWidth - 356),
          width: 340,
          zIndex: 1001,
        };
      })()
    : {
        position: "fixed",
        top: "50%",
        left: "50%",
        transform: "translate(-50%, -50%)",
        width: 380,
        zIndex: 1001,
      };

  return (
    <>
      {/* Dimmer: only when there's no spotlight (spotlight makes its own via box-shadow). */}
      {!rect ? (
        <div className="fixed inset-0 z-[1000] bg-slate-900/55" onClick={onSkip} aria-hidden />
      ) : null}
      {spotlight ? <div style={spotlight} /> : null}
      <div style={tipStyle} className="rounded-xl border border-slate-200 bg-white p-4 shadow-2xl">
        <div className="mb-1 text-[11px] font-semibold uppercase tracking-wide text-brand">
          Step {index + 1} of {total}
        </div>
        <h3 className="text-base font-semibold text-slate-800">{step.title}</h3>
        <p className="mt-1 text-sm text-slate-600">{step.body}</p>
        <div className="mt-4 flex items-center justify-between">
          <button onClick={onSkip} className="text-xs text-slate-400 hover:text-slate-600">
            Skip tour
          </button>
          <div className="flex gap-2">
            {index > 0 ? (
              <button
                onClick={onBack}
                className="rounded-lg border border-slate-300 px-3 py-1.5 text-sm font-medium text-slate-600 hover:bg-slate-50"
              >
                Back
              </button>
            ) : null}
            <button
              onClick={onNext}
              className="rounded-lg bg-brand px-3 py-1.5 text-sm font-medium text-white hover:opacity-90"
            >
              {index === total - 1 ? "Done" : "Next"}
            </button>
          </div>
        </div>
      </div>
    </>
  );
}
