import React from "react";
import { Series } from "remotion";

import { Architecture } from "./scenes/Architecture";
import { BarChart } from "./scenes/BarChart";
import { Close } from "./scenes/Close";
import { Hero } from "./scenes/Hero";
import { SceneWrapper } from "./scenes/SceneWrapper";
import { StatTrio } from "./scenes/StatTrio";
import { Statement } from "./scenes/Statement";
import { Team } from "./scenes/Team";
import { Timeline } from "./scenes/Timeline";
import { TwoColumn } from "./scenes/TwoColumn";
import { resolveTheme } from "./theme";
import type {
  ArchitectureContent,
  BarChartContent,
  CloseContent,
  HeroContent,
  PitchVideoProps,
  StatTrioContent,
  StatementContent,
  TeamContent,
  TimelineContent,
  TwoColumnContent,
} from "./types";

export function PitchVideo({ designTokens, scenes }: PitchVideoProps) {
  const theme = resolveTheme(designTokens);

  return (
    <Series>
      {scenes.map((scene) => (
        <Series.Sequence key={scene.id} durationInFrames={scene.frameCount} layout="none">
          <SceneWrapper theme={theme} variant={scene.variant} audioPath={scene.audioPath} frameCount={scene.frameCount}>
            {renderScene(scene.layout, scene.content, theme)}
          </SceneWrapper>
        </Series.Sequence>
      ))}
    </Series>
  );
}

function renderScene(layout: string, content: unknown, theme: ReturnType<typeof resolveTheme>) {
  switch (layout) {
    case "hero":
      return <Hero content={content as HeroContent} theme={theme} />;
    case "statement":
      return <Statement content={content as StatementContent} theme={theme} />;
    case "stat-trio":
      return <StatTrio content={content as StatTrioContent} theme={theme} />;
    case "two-column":
      return <TwoColumn content={content as TwoColumnContent} theme={theme} />;
    case "architecture":
      return <Architecture content={content as ArchitectureContent} theme={theme} />;
    case "bar-chart":
      return <BarChart content={content as BarChartContent} theme={theme} />;
    case "timeline":
      return <Timeline content={content as TimelineContent} theme={theme} />;
    case "team":
      return <Team content={content as TeamContent} theme={theme} />;
    case "close":
      return <Close content={content as CloseContent} theme={theme} />;
    default:
      throw new Error(`Unknown scene layout: ${layout}`);
  }
}
