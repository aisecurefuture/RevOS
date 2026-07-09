import React from "react";

import type { ResolvedTheme } from "../theme";
import type { TeamContent } from "../types";

export function Team({ content, theme }: { content: TeamContent; theme: ResolvedTheme }) {
  return (
    <div style={{ display: "flex", gap: 56 }}>
      {content.members.map((m, i) => (
        <div key={i} style={{ flex: 1, display: "flex", flexDirection: "column", gap: 8 }}>
          <div style={{ fontFamily: theme.fontHeading, fontSize: 38, fontWeight: 700 }}>{m.name}</div>
          <div style={{ fontFamily: theme.fontBody, fontSize: 22, color: theme.accent, fontWeight: 600 }}>
            {m.role}
          </div>
          {m.bio ? (
            <div style={{ fontFamily: theme.fontBody, fontSize: 20, opacity: 0.75, marginTop: 8, lineHeight: 1.4 }}>
              {m.bio}
            </div>
          ) : null}
        </div>
      ))}
    </div>
  );
}
