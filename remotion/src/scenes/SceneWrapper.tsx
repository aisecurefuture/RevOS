import React from "react";
import { AbsoluteFill, Audio, interpolate, staticFile, useCurrentFrame, useVideoConfig } from "remotion";

import type { ResolvedTheme } from "../theme";
import type { Variant } from "../types";

const FADE_FRAMES = 15;

export function SceneWrapper({
  theme, variant, audioPath, frameCount, children, padded = true,
}: {
  theme: ResolvedTheme;
  variant: Variant;
  /** Filename relative to the render's public dir (see remotion.config.ts) — NOT an absolute path. */
  audioPath: string;
  frameCount: number;
  children: React.ReactNode;
  padded?: boolean;
}) {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const fade = Math.min(FADE_FRAMES, Math.floor(fps / 2));

  const opacity = interpolate(
    frame,
    [0, fade, Math.max(fade, frameCount - fade), frameCount],
    [0, 1, 1, 0],
    { extrapolateLeft: "clamp", extrapolateRight: "clamp" },
  );

  const bg = variant === "dark" ? theme.bgDark : theme.bgLight;
  const color = variant === "dark" ? "#ffffff" : theme.text;

  return (
    <AbsoluteFill style={{ backgroundColor: bg, color, fontFamily: theme.fontBody }}>
      <Audio src={staticFile(audioPath)} />
      <AbsoluteFill
        style={{
          opacity,
          padding: padded ? "8% 10%" : 0,
          display: "flex",
          flexDirection: "column",
          justifyContent: "center",
        }}
      >
        {children}
      </AbsoluteFill>
    </AbsoluteFill>
  );
}
