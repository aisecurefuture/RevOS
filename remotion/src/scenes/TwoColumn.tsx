import React from "react";

import type { ResolvedTheme } from "../theme";
import type { TwoColumnContent } from "../types";

function Pane({ heading, body, theme }: { heading: string; body: string; theme: ResolvedTheme }) {
  return (
    <div style={{ flex: 1, display: "flex", flexDirection: "column", gap: 16 }}>
      <div style={{ fontFamily: theme.fontHeading, fontSize: 40, fontWeight: 700 }}>{heading}</div>
      <div style={{ fontFamily: theme.fontBody, fontSize: 26, opacity: 0.8, lineHeight: 1.4 }}>{body}</div>
    </div>
  );
}

export function TwoColumn({ content, theme }: { content: TwoColumnContent; theme: ResolvedTheme }) {
  return (
    <div style={{ display: "flex", gap: 64 }}>
      <Pane heading={content.left.heading} body={content.left.body} theme={theme} />
      <div style={{ width: 1, backgroundColor: theme.hairline, opacity: 0.6 }} />
      <Pane heading={content.right.heading} body={content.right.body} theme={theme} />
    </div>
  );
}
