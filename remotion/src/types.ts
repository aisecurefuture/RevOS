// Mirrors app/schemas/pitch_video.py's content models EXACTLY (field names
// match the Python side's `model_dump()` output verbatim — snake_case where
// Python used snake_case, e.g. BarChartContent.y_label). This file is the
// other half of the shared contract; if you change a content shape on the
// Python side, update it here too.

export type Variant = "light" | "dark";

export interface HeroContent {
  eyebrow?: string | null;
  headline: string;
  sub?: string | null;
}

export interface StatementContent {
  text: string;
  equation?: string[] | null;
}

export interface StatItem {
  value: string;
  label: string;
}

export interface StatTrioContent {
  stats: StatItem[];
}

export interface TwoColumnPane {
  heading: string;
  body: string;
}

export interface TwoColumnContent {
  left: TwoColumnPane;
  right: TwoColumnPane;
}

export interface ArchitectureBand {
  label: string;
  description?: string | null;
}

export interface ArchitectureContent {
  bands: ArchitectureBand[];
}

export interface BarSegment {
  label: string;
  value: number;
}

export interface Bar {
  category: string;
  segments: BarSegment[];
}

export interface BarChartContent {
  bars: Bar[];
  y_label?: string | null;
  note?: string | null;
}

export interface TimelineStep {
  label: string;
  description?: string | null;
}

export interface TimelineContent {
  steps: TimelineStep[];
}

export interface TeamMember {
  name: string;
  role: string;
  bio?: string | null;
}

export interface TeamContent {
  members: TeamMember[];
}

export interface CloseContent {
  headline: string;
  sub?: string | null;
}

// --- Schematic-native layouts -------------------------------------------------

export interface RevealLine {
  text: string;          // "" renders as a skeleton bar
  highlight: boolean;
}

export interface RevealPane {
  label: string;
  lines: RevealLine[];
}

export interface SplitRevealContent {
  left: RevealPane;
  right: RevealPane;
  caption?: string | null;
}

export interface VerdictLanesContent {
  lanes: string[];
  caption?: string | null;
}

export interface GridCard {
  title: string;
  value: string;
  open: boolean;
}

export interface CardGridContent {
  cards: GridCard[];
  caption?: string | null;
  note?: string | null;
}

export interface StackBlock {
  label: string;
  value: string;
}

export interface StackSummaryContent {
  blocks: StackBlock[];
  summary_label: string;
  summary_big: string;
  capline?: string | null;
  note?: string | null;
}

export interface TermsContent {
  label: string;
  big: string;
  sub?: string | null;
  chips: string[];
}

export type SceneContent =
  | HeroContent
  | StatementContent
  | StatTrioContent
  | TwoColumnContent
  | ArchitectureContent
  | BarChartContent
  | TimelineContent
  | TeamContent
  | CloseContent
  | SplitRevealContent
  | VerdictLanesContent
  | CardGridContent
  | StackSummaryContent
  | TermsContent;

export interface Chapter {
  num: string;
  label: string;
}

export type SceneLayout =
  | "hero"
  | "statement"
  | "stat-trio"
  | "two-column"
  | "architecture"
  | "bar-chart"
  | "timeline"
  | "team"
  | "close"
  | "split-reveal"
  | "verdict-lanes"
  | "card-grid"
  | "stack-summary"
  | "terms";

export interface SceneProps {
  id: string;
  layout: SceneLayout;
  variant: Variant;
  content: SceneContent;
  chapter?: Chapter | null;
  /** Substring of the headline/caption that gets the luminous underline sweep. */
  emphasis?: string | null;
  /** Hero background motif (schematic style): content stream / gate / none. */
  motif?: "stream" | "gate" | "none";
  /** Filename relative to the render's public dir — resolved via staticFile(), not a raw absolute path. */
  audioPath: string;
  frameStart: number;
  frameCount: number;
}

// Matches Brand.design_tokens's documented (all-optional) shape.
export interface DesignTokens {
  colors?: {
    bg_dark?: string;
    bg_light?: string;
    surface?: string;
    card?: string;
    text?: string;
    muted?: string;
    muted_on_dark?: string;
    hairline?: string;
    hairline_on_dark?: string;
    accent?: string;
    chart_ramp?: string[];
    // Schematic-style extras (all optional; defaults in theme.ts):
    panel?: string;        // card fill on the dark stage
    panel2?: string;       // brighter panel gradient stop
    stroke?: string;       // card/hairline stroke on the dark stage
    glow?: string;         // the luminous accent (underline sweep, gate, curve)
    good?: string;         // verdict green
    warn?: string;         // verdict amber
    bad?: string;          // verdict red
  };
  fonts?: {
    heading?: string;
    body?: string;
    display?: string;      // serif statement face (schematic style)
  };
  wordmark?: string;
  pillars?: string[];
}

export interface PitchVideoProps extends Record<string, unknown> {
  title: string;
  style?: "minimal" | "schematic";
  fps: number;
  width: number;
  height: number;
  designTokens: DesignTokens;
  scenes: SceneProps[];
}
