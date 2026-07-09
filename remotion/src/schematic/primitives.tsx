// The "precision schematic" motion vocabulary, ported from the reference
// animatic (motion_deck.html): staged rise-in entrances, the luminous
// underline sweep, streaming content chips, the glowing AI node and gate
// pylons, a self-drawing curve, and slow camera drift. All animation is
// frame-driven (no CSS keyframes) so renders are deterministic.
import React from "react";
import { interpolate, random, useCurrentFrame, useVideoConfig } from "remotion";

import type { ResolvedTheme } from "../theme";

// Stagger delays d0..d5 — matches the animatic's .rise .d1–.d5 rhythm.
export function riseDelay(step: number, fps: number): number {
  return Math.round(step * 0.4 * fps + 0.15 * fps);
}

/** Staged entrance: fade + 40px rise, starting at `delay` frames. */
export function Rise({
  delay, children, style,
}: { delay: number; children: React.ReactNode; style?: React.CSSProperties }) {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const t = interpolate(frame - delay, [0, 0.7 * fps], [0, 1], {
    extrapolateLeft: "clamp", extrapolateRight: "clamp",
  });
  const eased = 1 - Math.pow(1 - t, 3);
  return (
    <div style={{ opacity: eased, transform: `translateY(${(1 - eased) * 40}px)`, ...style }}>
      {children}
    </div>
  );
}

/** The luminous underline sweep — the storyboard's emphasis device. */
export function Em({
  text, emphasis, theme, sweepStart,
}: { text: string; emphasis?: string | null; theme: ResolvedTheme; sweepStart: number }) {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  if (!emphasis) return <>{text}</>;
  const idx = text.toLowerCase().indexOf(emphasis.toLowerCase());
  if (idx === -1) return <>{text}</>;
  const before = text.slice(0, idx);
  const match = text.slice(idx, idx + emphasis.length);
  const after = text.slice(idx + emphasis.length);
  const width = interpolate(frame - sweepStart, [0, 0.45 * fps], [0, 100], {
    extrapolateLeft: "clamp", extrapolateRight: "clamp",
  });
  return (
    <>
      {before}
      <span style={{ position: "relative", whiteSpace: "nowrap" }}>
        {match}
        <span
          style={{
            position: "absolute", left: 0, bottom: "-0.12em", height: "0.13em",
            width: `${width}%`,
            background: `linear-gradient(90deg, ${theme.glow}, ${theme.glow})`,
            boxShadow: `0 0 14px ${theme.glow}`,
          }}
        />
      </span>
      {after}
    </>
  );
}

/** A single skeleton content chip (the "untrusted content" unit). */
export function Chip({ theme, style }: { theme: ResolvedTheme; style?: React.CSSProperties }) {
  return (
    <div
      style={{
        width: 125, height: 77, border: `1px solid ${theme.stroke}`, borderRadius: 7,
        background: "rgba(18,36,60,0.7)", position: "absolute", ...style,
      }}
    >
      <div style={{ position: "absolute", left: "12%", top: "20%", width: "60%", height: "8%", background: theme.mutedOnDark, opacity: 0.5 }} />
      <div style={{ position: "absolute", left: "12%", top: "42%", width: "76%", height: "6%", background: theme.mutedOnDark, opacity: 0.3 }} />
      <div style={{ position: "absolute", left: "12%", top: "58%", width: "70%", height: "6%", background: theme.mutedOnDark, opacity: 0.3 }} />
    </div>
  );
}

/** Content chips streaming left→right across the stage (hook/gate scenes).
 * Deterministic per scene id via remotion's random(). If `gateX` is given
 * (0..1), chips visually dim as they pass the gate line. */
export function ChipStream({
  theme, seed, count = 9, gateX,
}: { theme: ResolvedTheme; seed: string; count?: number; gateX?: number }) {
  const frame = useCurrentFrame();
  const { width, height, fps } = useVideoConfig();
  const chips = new Array(count).fill(0).map((_, i) => {
    const top = random(`${seed}-top-${i}`) * 0.6 + 0.16;
    const speed = 5 + random(`${seed}-speed-${i}`) * 3; // seconds to cross
    const phase = random(`${seed}-phase-${i}`);
    const progress = ((frame / fps / speed) + phase) % 1;
    const x = progress * (width + 250) - 250;
    const past = gateX !== undefined && x > gateX * width;
    return (
      <Chip
        key={i} theme={theme}
        style={{ left: x, top: top * height, opacity: past ? 0.25 : 0.8 }}
      />
    );
  });
  return <div style={{ position: "absolute", inset: 0, overflow: "hidden" }}>{chips}</div>;
}

/** The glowing AI node (where all content is headed). */
export function AINode({ theme, style }: { theme: ResolvedTheme; style?: React.CSSProperties }) {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const bob = Math.sin((frame / fps) * (Math.PI / 3.5)) * 9;
  return (
    <div
      style={{
        position: "absolute", right: "3%", top: "34%", width: 165, height: 165,
        borderRadius: "50%", border: `2.5px solid ${theme.glow}`,
        boxShadow: `0 0 45px ${theme.glow}80`,
        display: "flex", alignItems: "center", justifyContent: "center",
        fontFamily: theme.fontDisplay, color: "#fff", fontSize: 32,
        transform: `translateY(${bob}px)`, ...style,
      }}
    >
      AI
    </div>
  );
}

/** The gate: two pylons + a pulsing scan plane between them. */
export function GatePylons({ theme, style }: { theme: ResolvedTheme; style?: React.CSSProperties }) {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const pulse = 0.35 + 0.65 * (0.5 + 0.5 * Math.sin((frame / fps) * (Math.PI / 1.2)));
  const pylon: React.CSSProperties = {
    position: "absolute", width: "14%", height: "100%",
    background: `linear-gradient(180deg, ${theme.panel2}, ${theme.panel})`,
    border: `1.5px solid ${theme.glow}`, borderRadius: 6,
    boxShadow: `0 0 22px ${theme.glow}50`,
  };
  return (
    <div style={{ position: "absolute", left: "44%", top: "14%", width: "12%", height: "72%", ...style }}>
      <div style={{ ...pylon, left: 0 }} />
      <div style={{ ...pylon, right: 0 }} />
      <div
        style={{
          position: "absolute", left: "14%", width: "72%", top: "4%", height: "92%",
          background: `linear-gradient(90deg, transparent, ${theme.glow}48, transparent)`,
          opacity: pulse,
        }}
      />
    </div>
  );
}

/** A curve that draws itself (the risk chart). */
export function DrawnCurve({ theme, startFrame }: { theme: ResolvedTheme; startFrame: number }) {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const progress = interpolate(frame - startFrame, [0, 3 * fps], [1200, 0], {
    extrapolateLeft: "clamp", extrapolateRight: "clamp",
  });
  return (
    <svg viewBox="0 0 600 340" style={{ width: "100%", height: "100%" }}>
      <line x1="40" y1="300" x2="580" y2="300" stroke={theme.stroke} />
      <line x1="40" y1="300" x2="40" y2="20" stroke={theme.stroke} />
      <path
        d="M40 290 C 200 280, 320 250, 420 170 S 560 40, 580 30"
        stroke={theme.glow} strokeWidth={4} fill="none"
        strokeDasharray={1200} strokeDashoffset={progress}
        style={{ filter: `drop-shadow(0 0 8px ${theme.glow}CC)` }}
      />
    </svg>
  );
}

/** Panel card in the schematic language. */
export function SCard({
  theme, style, children, dashed,
}: { theme: ResolvedTheme; style?: React.CSSProperties; children: React.ReactNode; dashed?: boolean }) {
  return (
    <div
      style={{
        background: dashed ? `${theme.glow}10` : theme.panel,
        border: dashed ? `2px dashed ${theme.glow}` : `1px solid ${theme.stroke}`,
        borderRadius: 10, boxShadow: "0 8px 24px rgba(0,0,0,0.35)",
        padding: "22px 28px", ...style,
      }}
    >
      {children}
    </div>
  );
}

/** Eyebrow label (letterspaced caps). */
export function Label({ theme, children }: { theme: ResolvedTheme; children: React.ReactNode }) {
  return (
    <div style={{ fontSize: 17, letterSpacing: "0.25em", color: theme.glow, fontWeight: 700, fontFamily: theme.fontBody }}>
      {children}
    </div>
  );
}

/** Slow camera drift (scale 1 → 1.045 over the scene). */
export function Drift({ frameCount, children }: { frameCount: number; children: React.ReactNode }) {
  const frame = useCurrentFrame();
  const scale = interpolate(frame, [0, frameCount], [1, 1.045], {
    extrapolateLeft: "clamp", extrapolateRight: "clamp",
  });
  return <div style={{ position: "absolute", inset: 0, transform: `scale(${scale})` }}>{children}</div>;
}
