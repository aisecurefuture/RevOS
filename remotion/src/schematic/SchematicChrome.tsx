import React from "react";
import { AbsoluteFill, Audio, interpolate, staticFile, useCurrentFrame, useVideoConfig } from "remotion";

import type { ResolvedTheme } from "../theme";
import type { Chapter } from "../types";
import { Drift } from "./primitives";

// Scene shell for the schematic style: deep-navy stage, ghost chapter
// numeral + letterspaced label top-left, progress dots bottom-center, slow
// camera drift on the content, fade transitions. The viewer always knows
// where they are — the storyboard's "recurring devices".
export function SchematicChrome({
  theme, chapter, sceneIndex, sceneCount, frameCount, audioPath, children,
}: {
  theme: ResolvedTheme;
  chapter?: Chapter | null;
  sceneIndex: number;
  sceneCount: number;
  frameCount: number;
  audioPath: string;
  children: React.ReactNode;
}) {
  const frame = useCurrentFrame();
  const { fps, height } = useVideoConfig();
  const fade = Math.min(15, Math.floor(fps / 2));
  const opacity = interpolate(
    frame,
    [0, fade, Math.max(fade, frameCount - fade), frameCount],
    [0, 1, 1, 0],
    { extrapolateLeft: "clamp", extrapolateRight: "clamp" },
  );

  return (
    <AbsoluteFill style={{ backgroundColor: theme.bgDark, color: theme.mutedOnDark, fontFamily: theme.fontBody }}>
      <Audio src={staticFile(audioPath)} />
      <AbsoluteFill style={{ opacity }}>
        <Drift frameCount={frameCount}>{children}</Drift>

        {chapter ? (
          <>
            <div
              style={{
                position: "absolute", top: "3%", left: "3%", fontFamily: theme.fontDisplay,
                fontSize: height * 0.16, lineHeight: 1, color: "#fff", opacity: 0.07, fontWeight: 700,
              }}
            >
              {chapter.num}
            </div>
            <div
              style={{
                position: "absolute", top: "4.2%", left: "3.2%", fontSize: 17,
                letterSpacing: "0.35em", color: theme.glow, fontWeight: 700,
              }}
            >
              {chapter.label}
            </div>
          </>
        ) : null}

        <div
          style={{
            position: "absolute", bottom: "2.5%", left: "50%", transform: "translateX(-50%)",
            display: "flex", gap: 11,
          }}
        >
          {new Array(sceneCount).fill(0).map((_, i) => (
            <div
              key={i}
              style={{
                width: 10, height: 10, borderRadius: "50%",
                background: i === sceneIndex ? theme.glow : theme.stroke,
                boxShadow: i === sceneIndex ? `0 0 11px ${theme.glow}` : undefined,
              }}
            />
          ))}
        </div>
      </AbsoluteFill>
    </AbsoluteFill>
  );
}
