import React from "react";

import type { ResolvedTheme } from "../theme";
import type { HeroContent } from "../types";

export function Hero({ content, theme }: { content: HeroContent; theme: ResolvedTheme }) {
  const mutedColor = "inherit";
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 24 }}>
      {content.eyebrow ? (
        <div
          style={{
            fontFamily: theme.fontBody, fontSize: 28, fontWeight: 600,
            letterSpacing: 2, textTransform: "uppercase", color: theme.accent,
          }}
        >
          {content.eyebrow}
        </div>
      ) : null}
      <div
        style={{
          fontFamily: theme.fontHeading, fontSize: 88, fontWeight: 800,
          lineHeight: 1.05, letterSpacing: -1, maxWidth: "90%",
        }}
      >
        {content.headline}
      </div>
      {content.sub ? (
        <div style={{ fontFamily: theme.fontBody, fontSize: 34, opacity: 0.75, maxWidth: "70%", color: mutedColor }}>
          {content.sub}
        </div>
      ) : null}
    </div>
  );
}
