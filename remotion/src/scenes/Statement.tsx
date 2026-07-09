import React from "react";

import type { ResolvedTheme } from "../theme";
import type { StatementContent } from "../types";

export function Statement({ content, theme }: { content: StatementContent; theme: ResolvedTheme }) {
  if (content.equation && content.equation.length > 0) {
    return (
      <div style={{ display: "flex", alignItems: "baseline", gap: 28, flexWrap: "wrap" }}>
        {content.equation.map((term, i) => (
          <React.Fragment key={i}>
            {i > 0 ? (
              <span style={{ fontFamily: theme.fontHeading, fontSize: 56, opacity: 0.4 }}>
                {i === content.equation!.length - 1 ? "=" : "+"}
              </span>
            ) : null}
            <span
              style={{
                fontFamily: theme.fontHeading, fontSize: 52, fontWeight: 700,
                color: i === content.equation!.length - 1 ? theme.accent : "inherit",
              }}
            >
              {term}
            </span>
          </React.Fragment>
        ))}
      </div>
    );
  }
  return (
    <div
      style={{
        fontFamily: theme.fontHeading, fontSize: 64, fontWeight: 700,
        lineHeight: 1.15, maxWidth: "85%",
      }}
    >
      {content.text}
    </div>
  );
}
