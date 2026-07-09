import React from "react";

import type { ResolvedTheme } from "../theme";
import type { StatTrioContent } from "../types";

export function StatTrio({ content, theme }: { content: StatTrioContent; theme: ResolvedTheme }) {
  return (
    <div style={{ display: "flex", justifyContent: "space-between", gap: 48 }}>
      {content.stats.map((s, i) => (
        <div key={i} style={{ display: "flex", flexDirection: "column", gap: 12, flex: 1 }}>
          <div style={{ fontFamily: theme.fontHeading, fontSize: 76, fontWeight: 800, color: theme.accent }}>
            {s.value}
          </div>
          <div style={{ fontFamily: theme.fontBody, fontSize: 26, opacity: 0.8, maxWidth: "90%" }}>
            {s.label}
          </div>
        </div>
      ))}
    </div>
  );
}
