import React from "react";
import {
  AbsoluteFill,
  Audio,
  Img,
  Sequence,
  interpolate,
  staticFile,
  useCurrentFrame,
} from "remotion";

import { resolveTheme, type ResolvedTheme } from "../theme";
import type { ListingVideoProps, PhotoSlot } from "./types";

// ---------------------------------------------------------------------------
// Ken Burns photo slide — alternates zoom-in/zoom-out with a slight drift so
// consecutive photos never move the same way. All motion is linear and small
// (4–8%) — listing photos must stay recognizable, not woozy.
// ---------------------------------------------------------------------------

function KenBurnsPhoto({
  src, slot, index,
}: { src: string; slot: PhotoSlot; index: number }) {
  const frame = useCurrentFrame(); // local to the Sequence
  const t = interpolate(frame, [0, slot.frame_count], [0, 1], {
    extrapolateLeft: "clamp", extrapolateRight: "clamp",
  });
  const zoomIn = index % 2 === 0;
  const scale = zoomIn ? 1.02 + 0.08 * t : 1.1 - 0.08 * t;
  const driftX = (index % 3 === 0 ? -1 : 1) * 12 * t; // px
  const driftY = (index % 4 < 2 ? -1 : 1) * 8 * t;

  // Quick crossfade at slide boundaries.
  const fade = interpolate(
    frame,
    [0, Math.min(10, slot.frame_count / 4), slot.frame_count - Math.min(10, slot.frame_count / 4), slot.frame_count],
    [0, 1, 1, 0],
    { extrapolateLeft: "clamp", extrapolateRight: "clamp" },
  );

  return (
    <AbsoluteFill style={{ opacity: fade, overflow: "hidden", backgroundColor: "#000" }}>
      <Img
        src={src}
        style={{
          width: "100%", height: "100%", objectFit: "cover",
          transform: `scale(${scale}) translate(${driftX}px, ${driftY}px)`,
        }}
      />
    </AbsoluteFill>
  );
}

// ---------------------------------------------------------------------------
// Overlays
// ---------------------------------------------------------------------------

function fmtNum(n?: number | null): string {
  if (n == null) return "";
  return Number.isInteger(n) ? String(n) : String(n);
}

function FactsBar({ p, theme }: { p: ListingVideoProps; theme: ResolvedTheme }) {
  const bits: string[] = [];
  if (p.beds) bits.push(`${fmtNum(p.beds)} bd`);
  if (p.baths) bits.push(`${fmtNum(p.baths)} ba`);
  if (p.sqft) bits.push(`${p.sqft.toLocaleString("en-US")} sqft`);
  if (bits.length === 0) return null;
  return (
    <div style={{
      display: "flex", gap: 18, justifyContent: "center",
      fontFamily: theme.fontBody, fontSize: 40, fontWeight: 600, color: "#fff",
    }}>
      {bits.map((b, i) => (
        <span key={b} style={{ display: "flex", gap: 18, alignItems: "center" }}>
          {i > 0 && <span style={{ opacity: 0.45 }}>·</span>}
          {b}
        </span>
      ))}
    </div>
  );
}

/** Persistent lower-third during the photo reel: address + facts chip. */
function LowerThird({ p, theme }: { p: ListingVideoProps; theme: ResolvedTheme }) {
  const frame = useCurrentFrame();
  const slide = interpolate(frame, [0, 18], [70, 0], {
    extrapolateLeft: "clamp", extrapolateRight: "clamp",
  });
  return (
    <AbsoluteFill style={{ justifyContent: "flex-end", pointerEvents: "none" }}>
      <div style={{
        margin: "0 40px 130px", padding: "26px 34px",
        transform: `translateY(${slide}px)`,
        borderRadius: 26,
        background: "rgba(8, 10, 14, 0.62)",
        backdropFilter: "blur(6px)",
        border: "1px solid rgba(255,255,255,0.14)",
      }}>
        <div style={{
          fontFamily: theme.fontHeading, fontSize: 44, fontWeight: 700,
          color: "#fff", lineHeight: 1.15,
        }}>
          {p.address}
        </div>
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginTop: 12 }}>
          <FactsBar p={p} theme={theme} />
          {p.priceText ? (
            <div style={{
              fontFamily: theme.fontHeading, fontSize: 44, fontWeight: 800, color: theme.glow,
            }}>
              {p.priceText}
            </div>
          ) : null}
        </div>
      </div>
    </AbsoluteFill>
  );
}

/** One feature chip per photo slot, rotating through the feature list. */
function FeatureChip({ text, theme }: { text: string; theme: ResolvedTheme }) {
  const frame = useCurrentFrame();
  const pop = interpolate(frame, [6, 20], [0, 1], {
    extrapolateLeft: "clamp", extrapolateRight: "clamp",
  });
  return (
    <AbsoluteFill style={{ alignItems: "center", pointerEvents: "none" }}>
      <div style={{
        marginTop: 170,
        transform: `scale(${0.8 + 0.2 * pop})`, opacity: pop,
        padding: "16px 30px", borderRadius: 999,
        background: theme.accent, color: "#fff",
        fontFamily: theme.fontBody, fontSize: 36, fontWeight: 700,
        boxShadow: "0 8px 30px rgba(0,0,0,0.35)",
      }}>
        ✓ {text}
      </div>
    </AbsoluteFill>
  );
}

// ---------------------------------------------------------------------------
// Intro / outro cards
// ---------------------------------------------------------------------------

function IntroCard({ p, theme, firstPhoto }: { p: ListingVideoProps; theme: ResolvedTheme; firstPhoto?: string }) {
  const frame = useCurrentFrame();
  const reveal = interpolate(frame, [0, 22], [0, 1], {
    extrapolateLeft: "clamp", extrapolateRight: "clamp",
  });
  return (
    <AbsoluteFill style={{ backgroundColor: theme.bgDark }}>
      {firstPhoto && (
        <Img
          src={firstPhoto}
          style={{
            width: "100%", height: "100%", objectFit: "cover",
            opacity: 0.42, transform: `scale(${1.06 + frame * 0.0008})`,
          }}
        />
      )}
      <AbsoluteFill style={{
        justifyContent: "center", alignItems: "center", padding: "0 70px", textAlign: "center",
        background: "linear-gradient(180deg, rgba(0,0,0,0.25), rgba(0,0,0,0.55))",
      }}>
        <div style={{
          opacity: reveal, transform: `translateY(${(1 - reveal) * 30}px)`,
          fontFamily: theme.fontBody, fontSize: 40, fontWeight: 700, letterSpacing: 6,
          textTransform: "uppercase", color: theme.glow, marginBottom: 30,
        }}>
          {p.listingType || "For Sale"}
        </div>
        <div style={{
          opacity: reveal, transform: `translateY(${(1 - reveal) * 40}px)`,
          fontFamily: theme.fontHeading, fontSize: 76, fontWeight: 800, color: "#fff", lineHeight: 1.12,
        }}>
          {p.address}
        </div>
        {p.priceText ? (
          <div style={{
            opacity: reveal,
            fontFamily: theme.fontHeading, fontSize: 60, fontWeight: 800,
            color: theme.glow, marginTop: 34,
          }}>
            {p.priceText}
          </div>
        ) : null}
      </AbsoluteFill>
    </AbsoluteFill>
  );
}

function OutroCard({ p, theme, lastPhoto }: { p: ListingVideoProps; theme: ResolvedTheme; lastPhoto?: string }) {
  const frame = useCurrentFrame();
  const reveal = interpolate(frame, [0, 20], [0, 1], {
    extrapolateLeft: "clamp", extrapolateRight: "clamp",
  });
  return (
    <AbsoluteFill style={{ backgroundColor: theme.bgDark }}>
      {lastPhoto && (
        <Img
          src={lastPhoto}
          style={{ width: "100%", height: "100%", objectFit: "cover", opacity: 0.28 }}
        />
      )}
      <AbsoluteFill style={{
        justifyContent: "center", alignItems: "center", padding: "0 80px", textAlign: "center",
        background: "linear-gradient(180deg, rgba(0,0,0,0.35), rgba(0,0,0,0.65))",
      }}>
        <div style={{
          opacity: reveal,
          fontFamily: theme.fontHeading, fontSize: 62, fontWeight: 800, color: "#fff", lineHeight: 1.15,
        }}>
          Schedule your private showing
        </div>
        {p.agentName ? (
          <div style={{
            opacity: reveal,
            fontFamily: theme.fontBody, fontSize: 46, fontWeight: 700, color: theme.glow, marginTop: 40,
          }}>
            {p.agentName}
          </div>
        ) : null}
        {p.brokerage ? (
          <div style={{
            opacity: reveal,
            fontFamily: theme.fontBody, fontSize: 36, color: "rgba(255,255,255,0.85)", marginTop: 12,
          }}>
            {p.brokerage}
          </div>
        ) : null}
        {p.agentPhone ? (
          <div style={{
            opacity: reveal,
            marginTop: 34, padding: "16px 36px", borderRadius: 999,
            background: theme.accent, color: "#fff",
            fontFamily: theme.fontBody, fontSize: 40, fontWeight: 700,
          }}>
            {p.agentPhone}
          </div>
        ) : null}
      </AbsoluteFill>
    </AbsoluteFill>
  );
}

// ---------------------------------------------------------------------------
// Composition
// ---------------------------------------------------------------------------

export function ListingVideo(props: ListingVideoProps) {
  const theme = resolveTheme(props.designTokens);
  const { timeline, photos, features } = props;
  const reelStart = timeline.intro_frames;
  const reelEnd = timeline.total_frames - timeline.outro_frames;

  return (
    <AbsoluteFill style={{ backgroundColor: "#000" }}>
      {/* Intro */}
      <Sequence durationInFrames={timeline.intro_frames} layout="none">
        <IntroCard
          p={props} theme={theme}
          firstPhoto={photos[0] ? staticFile(photos[0]) : undefined}
        />
      </Sequence>

      {/* Photo reel */}
      {timeline.photos.map((slot) => {
        const src = photos[slot.index];
        if (!src) return null;
        const feature = features[slot.index % Math.max(features.length, 1)];
        return (
          <Sequence
            key={slot.index}
            from={slot.frame_start}
            durationInFrames={slot.frame_count}
            layout="none"
          >
            <KenBurnsPhoto src={staticFile(src)} slot={slot} index={slot.index} />
            {feature && slot.index < features.length ? (
              <FeatureChip text={feature} theme={theme} />
            ) : null}
          </Sequence>
        );
      })}

      {/* Lower third across the whole reel */}
      <Sequence from={reelStart} durationInFrames={reelEnd - reelStart} layout="none">
        <LowerThird p={props} theme={theme} />
      </Sequence>

      {/* Outro */}
      <Sequence from={reelEnd} durationInFrames={timeline.outro_frames} layout="none">
        <OutroCard
          p={props} theme={theme}
          lastPhoto={photos[photos.length - 1] ? staticFile(photos[photos.length - 1]) : undefined}
        />
      </Sequence>

      {/* Narration starts right after the intro card begins settling */}
      <Sequence from={Math.min(15, timeline.intro_frames)} layout="none">
        <Audio src={staticFile(props.narrationPath)} />
      </Sequence>

      {/* Licensed music bed, ducked under the voice */}
      {props.musicPath ? (
        <Audio src={staticFile(props.musicPath)} volume={props.musicVolume ?? 0.14} loop />
      ) : null}
    </AbsoluteFill>
  );
}
