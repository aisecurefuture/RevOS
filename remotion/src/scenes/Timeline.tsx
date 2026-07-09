import React from "react";

import type { ResolvedTheme } from "../theme";
import type { TimelineContent } from "../types";

export function Timeline({ content, theme }: { content: TimelineContent; theme: ResolvedTheme }) {
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 40 }}>
      <div style={{ display: "flex", alignItems: "center" }}>
        {content.steps.map((_, i) => (
          <React.Fragment key={i}>
            <div style={{ width: 20, height: 20, borderRadius: 10, backgroundColor: theme.accent, flexShrink: 0 }} />
            {i < content.steps.length - 1 ? (
              <div style={{ flex: 1, height: 2, backgroundColor: theme.hairline }} />
            ) : null}
          </React.Fragment>
        ))}
      </div>
      <div style={{ display: "flex" }}>
        {content.steps.map((step, i) => (
          <div key={i} style={{ flex: i < content.steps.length - 1 ? 1 : "0 0 auto", paddingRight: 24 }}>
            <div style={{ fontFamily: theme.fontHeading, fontSize: 28, fontWeight: 700 }}>{step.label}</div>
            {step.description ? (
              <div style={{ fontFamily: theme.fontBody, fontSize: 18, opacity: 0.7, marginTop: 6 }}>
                {step.description}
              </div>
            ) : null}
          </div>
        ))}
      </div>
    </div>
  );
}
