import React from "react";

import type { ResolvedTheme } from "../theme";
import type { BarChartContent } from "../types";

const CHART_HEIGHT = 460;

// dataviz-skill compliance note: brand chart ramps (e.g. CyberArmor's
// grayscale-plus-one-accent) can fail the strict categorical hue-floor/
// contrast checks by design (a deliberately muted, minimalist palette). Per
// the skill's mitigation for that case, this chart never relies on hue
// alone: every segment has a legend label, every bar has a direct total
// label, and a 2px surface-color gap separates stacked segments.
export function BarChart({ content, theme }: { content: BarChartContent; theme: ResolvedTheme }) {
  const segmentNames = Array.from(new Set(content.bars.flatMap((b) => b.segments.map((s) => s.label))));
  const colorFor = (label: string) => {
    const i = segmentNames.indexOf(label);
    return theme.chartRamp[i % theme.chartRamp.length];
  };
  const maxTotal = Math.max(...content.bars.map((b) => b.segments.reduce((sum, s) => sum + s.value, 0)));

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 28 }}>
      {/* Legend — identity is never color-alone */}
      <div style={{ display: "flex", gap: 28 }}>
        {segmentNames.map((name) => (
          <div key={name} style={{ display: "flex", alignItems: "center", gap: 10 }}>
            <div style={{ width: 16, height: 16, borderRadius: 4, backgroundColor: colorFor(name) }} />
            <span style={{ fontFamily: theme.fontBody, fontSize: 22, opacity: 0.85 }}>{name}</span>
          </div>
        ))}
      </div>

      {/* Bars */}
      <div style={{ display: "flex", alignItems: "flex-end", gap: 40, height: CHART_HEIGHT }}>
        {content.bars.map((bar, i) => {
          const total = bar.segments.reduce((sum, s) => sum + s.value, 0);
          const barHeight = (total / maxTotal) * CHART_HEIGHT;
          return (
            <div key={i} style={{ display: "flex", flexDirection: "column", alignItems: "center", gap: 12, flex: 1 }}>
              <div style={{ fontFamily: theme.fontHeading, fontSize: 26, fontWeight: 700 }}>
                {total.toLocaleString()}
              </div>
              <div
                style={{
                  width: "100%", height: barHeight, display: "flex", flexDirection: "column-reverse",
                  border: `1px solid ${theme.hairline}`, borderRadius: 6, overflow: "hidden",
                }}
              >
                {bar.segments.map((seg, j) => (
                  <div
                    key={j}
                    style={{
                      height: `${(seg.value / total) * 100}%`,
                      backgroundColor: colorFor(seg.label),
                      // 2px surface-color gap between stacked segments (marks-and-anatomy.md).
                      borderTop: j > 0 ? `2px solid ${theme.bgLight}` : undefined,
                    }}
                  />
                ))}
              </div>
              <div style={{ fontFamily: theme.fontBody, fontSize: 22, opacity: 0.75 }}>{bar.category}</div>
            </div>
          );
        })}
      </div>

      {content.note ? (
        <div style={{ fontFamily: theme.fontBody, fontSize: 18, opacity: 0.55, fontStyle: "italic" }}>
          {content.note}
        </div>
      ) : null}
    </div>
  );
}
