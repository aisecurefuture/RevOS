import React from "react";

import type { ResolvedTheme } from "../theme";
import type { ArchitectureContent } from "../types";

export function Architecture({ content, theme }: { content: ArchitectureContent; theme: ResolvedTheme }) {
  return (
    <div style={{ display: "flex", flexDirection: "column", alignItems: "stretch" }}>
      {content.bands.map((band, i) => (
        <React.Fragment key={i}>
          {i > 0 ? (
            <div style={{ width: 2, height: 28, backgroundColor: theme.accent, alignSelf: "center", opacity: 0.6 }} />
          ) : null}
          <div
            style={{
              border: `1.5px solid ${theme.hairline}`,
              borderRadius: 12,
              padding: "24px 32px",
              display: "flex",
              flexDirection: "column",
              gap: 6,
            }}
          >
            <div style={{ fontFamily: theme.fontHeading, fontSize: 36, fontWeight: 700 }}>{band.label}</div>
            {band.description ? (
              <div style={{ fontFamily: theme.fontBody, fontSize: 22, opacity: 0.7 }}>{band.description}</div>
            ) : null}
          </div>
        </React.Fragment>
      ))}
    </div>
  );
}
