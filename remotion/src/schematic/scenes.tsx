// Schematic-style scene renderers — the "precision schematic" language from
// the reference animatic, one renderer per Deck Spec layout. Statement-class
// scenes use the display serif; labels/body use the sans. Every scene stages
// its elements with Rise() and puts at most one emphasis sweep on screen.
import React from "react";
import { useVideoConfig } from "remotion";

import type { ResolvedTheme } from "../theme";
import type {
  ArchitectureContent,
  BarChartContent,
  CardGridContent,
  CloseContent,
  HeroContent,
  SceneProps,
  SplitRevealContent,
  StackSummaryContent,
  StatTrioContent,
  StatementContent,
  TeamContent,
  TermsContent,
  TimelineContent,
  TwoColumnContent,
  VerdictLanesContent,
} from "../types";
import {
  AINode, Chip, ChipStream, DrawnCurve, Em, GatePylons, Label, Rise, SCard, riseDelay,
} from "./primitives";

type P<C> = { content: C; scene: SceneProps; theme: ResolvedTheme };

function Caption({ text, scene, theme, delayStep = 3, size = 34 }: {
  text: string; scene: SceneProps; theme: ResolvedTheme; delayStep?: number; size?: number;
}) {
  const { fps } = useVideoConfig();
  return (
    <div style={{ position: "absolute", left: "8%", right: "8%", top: "72%", textAlign: "center" }}>
      <Rise delay={riseDelay(delayStep, fps)}>
        <h1 style={{ fontFamily: theme.fontDisplay, fontSize: size, color: "#fff", lineHeight: 1.3, fontWeight: 700 }}>
          <Em text={text} emphasis={scene.emphasis} theme={theme} sweepStart={riseDelay(delayStep + 1, fps)} />
        </h1>
      </Rise>
    </div>
  );
}

// --- hero: full-screen statement over an optional stream/gate motif ---------
export function SHero({ content, scene, theme }: P<HeroContent>) {
  const { fps } = useVideoConfig();
  return (
    <>
      {scene.motif === "stream" || scene.motif === "gate" ? (
        <ChipStream theme={theme} seed={scene.id} gateX={scene.motif === "gate" ? 0.44 : undefined} />
      ) : null}
      {scene.motif === "gate" ? <GatePylons theme={theme} /> : null}
      {scene.motif === "stream" || scene.motif === "gate" ? <AINode theme={theme} /> : null}
      <div
        style={{
          position: "absolute", inset: 0, display: "flex", flexDirection: "column",
          alignItems: "center", justifyContent: scene.motif === "gate" ? "flex-end" : "center",
          textAlign: "center", padding: "0 12%", paddingBottom: scene.motif === "gate" ? "10%" : undefined,
        }}
      >
        {content.eyebrow ? (
          <Rise delay={riseDelay(0, fps)}><Label theme={theme}>{content.eyebrow}</Label></Rise>
        ) : null}
        <Rise delay={riseDelay(1, fps)}>
          <h1 style={{ fontFamily: theme.fontDisplay, fontSize: 66, color: "#fff", lineHeight: 1.25, fontWeight: 700, marginTop: 18 }}>
            <Em text={content.headline} emphasis={scene.emphasis} theme={theme} sweepStart={riseDelay(2, fps)} />
          </h1>
        </Rise>
        {content.sub ? (
          <Rise delay={riseDelay(2, fps)}>
            <div style={{ fontSize: 26, color: theme.mutedOnDark, marginTop: 20 }}>{content.sub}</div>
          </Rise>
        ) : null}
      </div>
    </>
  );
}

// --- statement ----------------------------------------------------------------
export function SStatement({ content, scene, theme }: P<StatementContent>) {
  const { fps } = useVideoConfig();
  if (content.equation && content.equation.length > 0) {
    return (
      <div style={{ position: "absolute", inset: 0, display: "flex", alignItems: "center", justifyContent: "center", gap: 40, flexWrap: "wrap", padding: "0 8%" }}>
        {content.equation.map((term, i) => (
          <React.Fragment key={i}>
            {i > 0 ? (
              <span style={{ fontFamily: theme.fontDisplay, fontSize: 52, color: theme.mutedOnDark }}>
                {i === content.equation!.length - 1 ? "=" : "+"}
              </span>
            ) : null}
            <Rise delay={riseDelay(i, fps)}>
              <SCard theme={theme} dashed={i === content.equation!.length - 1}>
                <span style={{ fontFamily: theme.fontDisplay, fontSize: 42, fontWeight: 700, color: i === content.equation!.length - 1 ? theme.glow : "#fff" }}>
                  {term}
                </span>
              </SCard>
            </Rise>
          </React.Fragment>
        ))}
      </div>
    );
  }
  return (
    <div style={{ position: "absolute", inset: 0, display: "flex", alignItems: "center", justifyContent: "center", textAlign: "center", padding: "0 12%" }}>
      <Rise delay={riseDelay(0, fps)}>
        <h1 style={{ fontFamily: theme.fontDisplay, fontSize: 62, color: "#fff", lineHeight: 1.3, fontWeight: 700 }}>
          <Em text={content.text} emphasis={scene.emphasis} theme={theme} sweepStart={riseDelay(2, fps)} />
        </h1>
      </Rise>
    </div>
  );
}

// --- stat-trio: 1 stat = drawn risk curve + card; else staggered stat cards ---
export function SStatTrio({ content, scene, theme }: P<StatTrioContent>) {
  const { fps } = useVideoConfig();
  if (content.stats.length === 1) {
    const s = content.stats[0];
    return (
      <>
        <div style={{ position: "absolute", left: "8%", top: "24%", width: "46%", height: "50%" }}>
          <DrawnCurve theme={theme} startFrame={riseDelay(0, fps)} />
        </div>
        <div style={{ position: "absolute", right: "8%", top: "30%", width: "31%" }}>
          <Rise delay={riseDelay(2, fps)}>
            <SCard theme={theme}>
              <b style={{ display: "block", fontFamily: theme.fontDisplay, fontSize: 62, color: "#fff" }}>{s.value}</b>
              <div style={{ fontSize: 22, color: theme.mutedOnDark, lineHeight: 1.4, marginTop: 8 }}>
                <Em text={s.label} emphasis={scene.emphasis} theme={theme} sweepStart={riseDelay(3, fps)} />
              </div>
            </SCard>
          </Rise>
        </div>
      </>
    );
  }
  return (
    <div style={{ position: "absolute", left: "8%", right: "8%", top: "32%", display: "flex", gap: 28 }}>
      {content.stats.map((s, i) => (
        <Rise key={i} delay={riseDelay(i, fps)} style={{ flex: 1 }}>
          <SCard theme={theme} style={{ height: "100%" }}>
            <b style={{ display: "block", fontFamily: theme.fontDisplay, fontSize: 54, color: theme.glow }}>{s.value}</b>
            <div style={{ fontSize: 20, color: theme.mutedOnDark, lineHeight: 1.4, marginTop: 8 }}>{s.label}</div>
          </SCard>
        </Rise>
      ))}
    </div>
  );
}

// --- two-column ---------------------------------------------------------------
export function STwoColumn({ content, scene, theme }: P<TwoColumnContent>) {
  const { fps } = useVideoConfig();
  const pane = (p: { heading: string; body: string }, i: number) => (
    <Rise delay={riseDelay(i * 2, fps)} style={{ flex: 1 }}>
      <SCard theme={theme} style={{ height: "100%" }}>
        <Label theme={theme}>{p.heading.toUpperCase()}</Label>
        <div style={{ fontSize: 24, color: theme.mutedOnDark, lineHeight: 1.5, marginTop: 16 }}>{p.body}</div>
      </SCard>
    </Rise>
  );
  return (
    <div style={{ position: "absolute", left: "10%", right: "10%", top: "28%", height: "44%", display: "flex", gap: 36 }}>
      {pane(content.left, 0)}
      {pane(content.right, 1)}
    </div>
  );
}

// --- architecture: gate pylons + bands as scan stages -------------------------
export function SArchitecture({ content, scene, theme }: P<ArchitectureContent>) {
  const { fps } = useVideoConfig();
  return (
    <>
      <ChipStream theme={theme} seed={scene.id} count={6} gateX={0.44} />
      <GatePylons theme={theme} style={{ top: "12%", height: "52%" }} />
      <AINode theme={theme} style={{ top: "22%" }} />
      <div style={{ position: "absolute", left: "8%", right: "8%", top: "70%", display: "flex", gap: 24, justifyContent: "center" }}>
        {content.bands.map((band, i) => (
          <Rise key={i} delay={riseDelay(i + 1, fps)} style={{ flex: 1, maxWidth: 420 }}>
            <SCard theme={theme}>
              <b style={{ fontFamily: theme.fontDisplay, fontSize: 28, color: "#fff", display: "block" }}>{band.label}</b>
              {band.description ? (
                <div style={{ fontSize: 17, color: theme.mutedOnDark, marginTop: 6, lineHeight: 1.4 }}>{band.description}</div>
              ) : null}
            </SCard>
          </Rise>
        ))}
      </div>
    </>
  );
}

// --- bar-chart ------------------------------------------------------------------
export function SBarChart({ content, scene, theme }: P<BarChartContent>) {
  const { fps } = useVideoConfig();
  const segmentNames = Array.from(new Set(content.bars.flatMap((b) => b.segments.map((s) => s.label))));
  const colorFor = (label: string) => theme.chartRamp[segmentNames.indexOf(label) % theme.chartRamp.length];
  const maxTotal = Math.max(...content.bars.map((b) => b.segments.reduce((sum, s) => sum + s.value, 0)));
  const CHART_H = 380;
  return (
    <div style={{ position: "absolute", left: "9%", right: "9%", top: "20%" }}>
      <div style={{ display: "flex", gap: 26, marginBottom: 22 }}>
        {segmentNames.map((name) => (
          <div key={name} style={{ display: "flex", alignItems: "center", gap: 9 }}>
            <div style={{ width: 15, height: 15, borderRadius: 4, backgroundColor: colorFor(name), boxShadow: `0 0 9px ${colorFor(name)}70` }} />
            <span style={{ fontSize: 19, color: theme.mutedOnDark }}>{name}</span>
          </div>
        ))}
      </div>
      <div style={{ display: "flex", alignItems: "flex-end", gap: 34, height: CHART_H }}>
        {content.bars.map((bar, i) => {
          const total = bar.segments.reduce((sum, s) => sum + s.value, 0);
          return (
            <Rise key={i} delay={riseDelay(i, fps)} style={{ flex: 1, display: "flex", flexDirection: "column", alignItems: "center", gap: 10, height: "100%", justifyContent: "flex-end" }}>
              <div style={{ fontFamily: theme.fontDisplay, fontSize: 24, fontWeight: 700, color: "#fff" }}>{total.toLocaleString()}</div>
              <div style={{ width: "100%", height: (total / maxTotal) * (CHART_H - 60), display: "flex", flexDirection: "column-reverse", border: `1px solid ${theme.stroke}`, borderRadius: 6, overflow: "hidden", boxShadow: `0 0 18px ${theme.glow}20` }}>
                {bar.segments.map((seg, j) => (
                  <div key={j} style={{ height: `${(seg.value / total) * 100}%`, backgroundColor: colorFor(seg.label), borderTop: j > 0 ? `2px solid ${theme.bgDark}` : undefined }} />
                ))}
              </div>
              <div style={{ fontSize: 19, color: theme.mutedOnDark }}>{bar.category}</div>
            </Rise>
          );
        })}
      </div>
      {content.note ? (
        <Rise delay={riseDelay(content.bars.length, fps)}>
          <div style={{ fontSize: 17, color: theme.mutedOnDark, fontStyle: "italic", marginTop: 18 }}>{content.note}</div>
        </Rise>
      ) : null}
    </div>
  );
}

// --- timeline -------------------------------------------------------------------
export function STimeline({ content, scene, theme }: P<TimelineContent>) {
  const { fps } = useVideoConfig();
  return (
    <div style={{ position: "absolute", left: "10%", right: "10%", top: "38%" }}>
      <div style={{ display: "flex", alignItems: "center" }}>
        {content.steps.map((_, i) => (
          <React.Fragment key={i}>
            <Rise delay={riseDelay(i, fps)}>
              <div style={{ width: 20, height: 20, borderRadius: "50%", background: theme.glow, boxShadow: `0 0 14px ${theme.glow}`, flexShrink: 0 }} />
            </Rise>
            {i < content.steps.length - 1 ? <div style={{ flex: 1, height: 2, background: theme.stroke }} /> : null}
          </React.Fragment>
        ))}
      </div>
      <div style={{ display: "flex", marginTop: 26 }}>
        {content.steps.map((step, i) => (
          <Rise key={i} delay={riseDelay(i, fps)} style={{ flex: i < content.steps.length - 1 ? 1 : "0 0 auto", paddingRight: 20 }}>
            <div style={{ fontFamily: theme.fontDisplay, fontSize: 27, fontWeight: 700, color: "#fff" }}>{step.label}</div>
            {step.description ? <div style={{ fontSize: 17, color: theme.mutedOnDark, marginTop: 6 }}>{step.description}</div> : null}
          </Rise>
        ))}
      </div>
    </div>
  );
}

// --- team -----------------------------------------------------------------------
export function STeam({ content, scene, theme }: P<TeamContent>) {
  const { fps } = useVideoConfig();
  return (
    <div style={{ position: "absolute", left: "12%", right: "12%", top: "30%", display: "flex", gap: 44 }}>
      {content.members.map((m, i) => (
        <Rise key={i} delay={riseDelay(i, fps)} style={{ flex: 1 }}>
          <SCard theme={theme} style={{ height: "100%" }}>
            <b style={{ fontFamily: theme.fontDisplay, fontSize: 34, color: "#fff", display: "block" }}>{m.name}</b>
            <div style={{ fontSize: 20, color: theme.glow, fontWeight: 700, marginTop: 6 }}>{m.role}</div>
            {m.bio ? <div style={{ fontSize: 18, color: theme.mutedOnDark, marginTop: 12, lineHeight: 1.45 }}>{m.bio}</div> : null}
          </SCard>
        </Rise>
      ))}
    </div>
  );
}

// --- close ----------------------------------------------------------------------
export function SClose({ content, scene, theme }: P<CloseContent>) {
  const { fps } = useVideoConfig();
  return (
    <div style={{ position: "absolute", inset: 0, display: "flex", flexDirection: "column", alignItems: "center", justifyContent: "center", textAlign: "center", padding: "0 14%" }}>
      <Rise delay={riseDelay(0, fps)}>
        <div
          style={{
            width: 150, height: 150, borderRadius: "50%", border: `2.5px solid ${theme.glow}`,
            boxShadow: `0 0 55px ${theme.glow}80`, margin: "0 auto 28px",
            display: "flex", alignItems: "center", justifyContent: "center",
            fontFamily: theme.fontDisplay, fontSize: 44, color: "#fff",
          }}
        >
          {(theme.wordmark || "•").split(" ").map((w) => w[0]).join("").slice(0, 2).toUpperCase()}
        </div>
      </Rise>
      <Rise delay={riseDelay(1, fps)}>
        <h1 style={{ fontFamily: theme.fontDisplay, fontSize: 52, color: "#fff", fontWeight: 700 }}>
          <Em text={content.headline} emphasis={scene.emphasis} theme={theme} sweepStart={riseDelay(2, fps)} />
        </h1>
      </Rise>
      {content.sub ? (
        <Rise delay={riseDelay(2, fps)}>
          <div style={{ fontSize: 23, color: theme.mutedOnDark, marginTop: 18 }}>{content.sub}</div>
        </Rise>
      ) : null}
      {theme.wordmark ? (
        <Rise delay={riseDelay(3, fps)}>
          <div style={{ display: "inline-block", marginTop: 30, padding: "15px 42px", border: `1.5px solid ${theme.glow}`, borderRadius: 8, color: "#fff", fontSize: 21, fontWeight: 700 }}>
            {theme.wordmark}
          </div>
        </Rise>
      ) : null}
    </div>
  );
}

// --- split-reveal ---------------------------------------------------------------
export function SSplitReveal({ content, scene, theme }: P<SplitRevealContent>) {
  const { fps } = useVideoConfig();
  const pane = (p: SplitRevealContent["left"], i: number) => (
    <Rise delay={riseDelay(i * 2, fps)} style={{ flex: 1 }}>
      <SCard theme={theme} style={{ height: "100%" }}>
        <Label theme={theme}>{p.label}</Label>
        <div style={{ marginTop: 14 }}>
          {p.lines.map((line, j) =>
            line.text ? (
              <div
                key={j}
                style={{
                  fontFamily: "ui-monospace, Menlo, monospace", fontSize: 19, margin: "9px 0",
                  color: line.highlight ? theme.glow : theme.mutedOnDark,
                  textShadow: line.highlight ? `0 0 11px ${theme.glow}E0` : undefined,
                }}
              >
                {line.text}
              </div>
            ) : (
              <div key={j} style={{ height: 13, background: theme.stroke, opacity: 0.6, borderRadius: 3, margin: "11px 0", width: `${88 - (j * 17) % 34}%` }} />
            ),
          )}
        </div>
      </SCard>
    </Rise>
  );
  return (
    <>
      <div style={{ position: "absolute", left: "10%", right: "10%", top: "20%", height: "46%", display: "flex", gap: 30 }}>
        {pane(content.left, 0)}
        {pane(content.right, 1)}
      </div>
      {content.caption ? <Caption text={content.caption} scene={scene} theme={theme} size={30} /> : null}
    </>
  );
}

// --- verdict-lanes ---------------------------------------------------------------
export function SVerdictLanes({ content, scene, theme }: P<VerdictLanesContent>) {
  const { fps } = useVideoConfig();
  const laneColors = [theme.good, theme.warn, theme.glow, theme.bad, theme.mutedOnDark, theme.accent];
  return (
    <>
      <div style={{ position: "absolute", left: "8%", right: "8%", top: "22%", height: "44%", display: "flex", flexDirection: "column", justifyContent: "space-between" }}>
        {content.lanes.map((lane, i) => (
          <Rise key={i} delay={riseDelay(i, fps)}>
            <div style={{ display: "flex", alignItems: "center", gap: 20 }}>
              <div style={{ width: 165, textAlign: "center", padding: "9px 0", borderRadius: 6, fontWeight: 700, fontSize: 21, color: theme.bgDark, background: laneColors[i % laneColors.length] }}>
                {lane}
              </div>
              <div style={{ flex: 1, height: 1.5, background: theme.stroke, position: "relative" }}>
                <div
                  style={{
                    position: "absolute", right: 0, top: -19, width: 38, height: 38, borderRadius: "50%",
                    border: `1.5px solid ${theme.good}`, color: theme.good, background: theme.panel,
                    display: "flex", alignItems: "center", justifyContent: "center", fontSize: 17,
                  }}
                >
                  ✓
                </div>
              </div>
            </div>
          </Rise>
        ))}
      </div>
      {content.caption ? <Caption text={content.caption} scene={scene} theme={theme} delayStep={content.lanes.length} size={30} /> : null}
    </>
  );
}

// --- card-grid --------------------------------------------------------------------
export function SCardGrid({ content, scene, theme }: P<CardGridContent>) {
  const { fps } = useVideoConfig();
  return (
    <>
      <div style={{ position: "absolute", left: "7%", right: "7%", top: "18%", display: "grid", gridTemplateColumns: "repeat(3, 1fr)", gap: 20 }}>
        {content.cards.map((card, i) => (
          <Rise key={i} delay={riseDelay(i, fps)}>
            <SCard theme={theme} dashed={card.open} style={{ padding: "20px 26px" }}>
              <b style={{ color: card.open ? theme.glow : "#fff", fontSize: 21, display: "block" }}>{card.title}</b>
              <span style={{ color: card.open ? theme.glow : theme.good, fontSize: 25, fontWeight: 700 }}>{card.value}</span>
            </SCard>
          </Rise>
        ))}
      </div>
      {content.caption ? <Caption text={content.caption} scene={scene} theme={theme} delayStep={Math.min(content.cards.length, 5)} size={34} /> : null}
      {content.note ? (
        <div style={{ position: "absolute", bottom: "5.5%", left: "8%", right: "8%", textAlign: "center" }}>
          <Rise delay={riseDelay(Math.min(content.cards.length, 5), fps)}>
            <span style={{ fontSize: 16, color: theme.mutedOnDark, fontStyle: "italic" }}>{content.note}</span>
          </Rise>
        </div>
      ) : null}
    </>
  );
}

// --- stack-summary ------------------------------------------------------------------
export function SStackSummary({ content, scene, theme }: P<StackSummaryContent>) {
  const { fps } = useVideoConfig();
  // The compliance rule from the storyboard: the disclaimer note appears in
  // the SAME beat as the summary card (delay index identical) — never after.
  const summaryStep = content.blocks.length;
  return (
    <>
      <div style={{ position: "absolute", left: "8%", top: "20%", width: "48%", height: "52%", display: "flex", flexDirection: "column-reverse", gap: 18 }}>
        {content.blocks.map((block, i) => (
          <Rise key={i} delay={riseDelay(i, fps)}>
            <SCard theme={theme} style={{ display: "flex", justifyContent: "space-between", alignItems: "center", padding: "18px 26px" }}>
              <b style={{ color: "#fff", fontSize: 23 }}>{block.label}</b>
              <span style={{ color: theme.good, fontWeight: 700, fontSize: 23 }}>{block.value}</span>
            </SCard>
          </Rise>
        ))}
      </div>
      <div style={{ position: "absolute", right: "7%", top: "24%", width: "30%" }}>
        <Rise delay={riseDelay(summaryStep, fps)}>
          <SCard theme={theme} style={{ textAlign: "center", padding: "28px" }}>
            <Label theme={theme}>{content.summary_label}</Label>
            <span style={{ display: "block", fontFamily: theme.fontDisplay, fontSize: 44, color: "#fff", marginTop: 14, lineHeight: 1.25 }}>
              {content.summary_big}
            </span>
            {content.capline ? (
              <div style={{ marginTop: 18, paddingTop: 18, borderTop: `1px solid ${theme.stroke}`, color: theme.glow, fontSize: 22, fontWeight: 700 }}>
                <Em text={content.capline} emphasis={scene.emphasis} theme={theme} sweepStart={riseDelay(summaryStep + 1, fps)} />
              </div>
            ) : null}
          </SCard>
        </Rise>
      </div>
      {content.note ? (
        <div style={{ position: "absolute", bottom: "7%", left: "8%", right: "8%", textAlign: "center" }}>
          <Rise delay={riseDelay(summaryStep, fps)}>
            <span style={{ fontSize: 17, color: theme.mutedOnDark, fontStyle: "italic" }}>{content.note}</span>
          </Rise>
        </div>
      ) : null}
    </>
  );
}

// --- terms ---------------------------------------------------------------------------
export function STerms({ content, scene, theme }: P<TermsContent>) {
  const { fps } = useVideoConfig();
  return (
    <>
      <div style={{ position: "absolute", left: "29%", width: "42%", top: "20%" }}>
        <Rise delay={riseDelay(0, fps)}>
          <SCard theme={theme} style={{ textAlign: "center", padding: "36px" }}>
            <Label theme={theme}>{content.label}</Label>
            <div style={{ fontFamily: theme.fontDisplay, fontSize: 52, color: "#fff", marginTop: 14 }}>
              <Em text={content.big} emphasis={scene.emphasis} theme={theme} sweepStart={riseDelay(1, fps)} />
            </div>
            {content.sub ? <div style={{ color: theme.mutedOnDark, fontSize: 21, marginTop: 12 }}>{content.sub}</div> : null}
          </SCard>
        </Rise>
      </div>
      <div style={{ position: "absolute", left: "12%", right: "12%", top: "62%", display: "flex", gap: 22, justifyContent: "center" }}>
        {content.chips.map((chip, i) => (
          <Rise key={i} delay={riseDelay(i + 1, fps)}>
            <SCard theme={theme} style={{ padding: "13px 24px", fontSize: 19, color: theme.mutedOnDark }}>{chip}</SCard>
          </Rise>
        ))}
      </div>
    </>
  );
}
