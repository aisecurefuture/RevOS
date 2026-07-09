import React from "react";

import type { ResolvedTheme } from "../theme";
import type { CloseContent } from "../types";

export function Close({ content, theme }: { content: CloseContent; theme: ResolvedTheme }) {
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 24, alignItems: "flex-start" }}>
      <div style={{ fontFamily: theme.fontHeading, fontSize: 72, fontWeight: 800, lineHeight: 1.1, maxWidth: "85%" }}>
        {content.headline}
      </div>
      {content.sub ? (
        <div style={{ fontFamily: theme.fontBody, fontSize: 30, opacity: 0.75 }}>{content.sub}</div>
      ) : null}
      {theme.wordmark ? (
        <div
          style={{
            fontFamily: theme.fontBody, fontSize: 22, fontWeight: 600, letterSpacing: 1,
            marginTop: 32, color: theme.accent,
          }}
        >
          {theme.wordmark}
        </div>
      ) : null}
    </div>
  );
}
