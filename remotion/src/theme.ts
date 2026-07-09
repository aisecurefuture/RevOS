// Resolves a Brand's (possibly partial/empty) design_tokens into a fully
// filled theme. Defaults come from the dataviz skill's validated reference
// palette (references/palette.md) — colorblind-safe, contrast-checked — so a
// brand with NO configured tokens still gets a good, accessible look, not
// hardcoded gray boxes. Every brand-specific value (CyberArmor's included)
// comes entirely from Brand.design_tokens; nothing brand-specific lives here.
import type { DesignTokens } from "./types";

export interface ResolvedTheme {
  bgDark: string;
  bgLight: string;
  surface: string;
  card: string;
  text: string;
  muted: string;
  mutedOnDark: string;
  hairline: string;
  hairlineOnDark: string;
  accent: string;
  chartRamp: string[];
  fontHeading: string;
  fontBody: string;
  wordmark: string | null;
  pillars: string[];
}

const SYSTEM_SANS =
  'system-ui, -apple-system, "Segoe UI", Roboto, Helvetica, Arial, sans-serif';

// The dataviz skill's validated default categorical palette (light-mode steps).
const DEFAULT_CHART_RAMP = [
  "#2a78d6", "#1baf7a", "#eda100", "#008300",
  "#4a3aa7", "#e34948", "#e87ba4", "#eb6834",
];

export function resolveTheme(tokens: DesignTokens | null | undefined): ResolvedTheme {
  const c = tokens?.colors ?? {};
  const f = tokens?.fonts ?? {};
  return {
    bgDark: c.bg_dark ?? "#0d0d0d",
    bgLight: c.bg_light ?? "#f9f9f7",
    surface: c.surface ?? "#fcfcfb",
    card: c.card ?? "#ffffff",
    text: c.text ?? "#0b0b0b",
    muted: c.muted ?? "#52514e",
    mutedOnDark: c.muted_on_dark ?? "#c3c2b7",
    hairline: c.hairline ?? "#e1e0d9",
    hairlineOnDark: c.hairline_on_dark ?? "#2c2c2a",
    accent: c.accent ?? "#2a78d6",
    chartRamp: c.chart_ramp && c.chart_ramp.length > 0 ? c.chart_ramp : DEFAULT_CHART_RAMP,
    fontHeading: f.heading || SYSTEM_SANS,
    fontBody: f.body || SYSTEM_SANS,
    wordmark: tokens?.wordmark ?? null,
    pillars: tokens?.pillars ?? [],
  };
}
