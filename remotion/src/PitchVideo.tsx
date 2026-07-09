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
import { SchematicChrome } from "./schematic/SchematicChrome";
import {
  SArchitecture, SBarChart, SCardGrid, SClose, SHero, SSplitReveal, SStackSummary,
  SStatTrio, SStatement, STeam, STerms, STimeline, STwoColumn, SVerdictLanes,
} from "./schematic/scenes";
import { resolveTheme } from "./theme";
import type {
  ArchitectureContent,
  BarChartContent,
  CardGridContent,
  CloseContent,
  HeroContent,
  PitchVideoProps,
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
} from "./types";

// Layouts that only exist in the schematic vocabulary — they render
// schematic-style regardless of the deck's declared style.
const SCHEMATIC_ONLY = new Set(["split-reveal", "verdict-lanes", "card-grid", "stack-summary", "terms"]);

export function PitchVideo({ designTokens, scenes, style }: PitchVideoProps) {
  const theme = resolveTheme(designTokens);
  const deckStyle = style ?? "minimal";

  return (
    <Series>
      {scenes.map((scene, index) => {
        const schematic = deckStyle === "schematic" || SCHEMATIC_ONLY.has(scene.layout);
        return (
          <Series.Sequence key={scene.id} durationInFrames={scene.frameCount} layout="none">
            {schematic ? (
              <SchematicChrome
                theme={theme} chapter={scene.chapter} sceneIndex={index} sceneCount={scenes.length}
                frameCount={scene.frameCount} audioPath={scene.audioPath}
              >
                {renderSchematic(scene, theme)}
              </SchematicChrome>
            ) : (
              <SceneWrapper theme={theme} variant={scene.variant} audioPath={scene.audioPath} frameCount={scene.frameCount}>
                {renderMinimal(scene, theme)}
              </SceneWrapper>
            )}
          </Series.Sequence>
        );
      })}
    </Series>
  );
}

function renderSchematic(scene: SceneProps, theme: ReturnType<typeof resolveTheme>) {
  const p = { scene, theme } as const;
  switch (scene.layout) {
    case "hero":
      return <SHero content={scene.content as HeroContent} {...p} />;
    case "statement":
      return <SStatement content={scene.content as StatementContent} {...p} />;
    case "stat-trio":
      return <SStatTrio content={scene.content as StatTrioContent} {...p} />;
    case "two-column":
      return <STwoColumn content={scene.content as TwoColumnContent} {...p} />;
    case "architecture":
      return <SArchitecture content={scene.content as ArchitectureContent} {...p} />;
    case "bar-chart":
      return <SBarChart content={scene.content as BarChartContent} {...p} />;
    case "timeline":
      return <STimeline content={scene.content as TimelineContent} {...p} />;
    case "team":
      return <STeam content={scene.content as TeamContent} {...p} />;
    case "close":
      return <SClose content={scene.content as CloseContent} {...p} />;
    case "split-reveal":
      return <SSplitReveal content={scene.content as SplitRevealContent} {...p} />;
    case "verdict-lanes":
      return <SVerdictLanes content={scene.content as VerdictLanesContent} {...p} />;
    case "card-grid":
      return <SCardGrid content={scene.content as CardGridContent} {...p} />;
    case "stack-summary":
      return <SStackSummary content={scene.content as StackSummaryContent} {...p} />;
    case "terms":
      return <STerms content={scene.content as TermsContent} {...p} />;
    default:
      throw new Error(`Unknown scene layout: ${scene.layout}`);
  }
}

function renderMinimal(scene: SceneProps, theme: ReturnType<typeof resolveTheme>) {
  switch (scene.layout) {
    case "hero":
      return <Hero content={scene.content as HeroContent} theme={theme} />;
    case "statement":
      return <Statement content={scene.content as StatementContent} theme={theme} />;
    case "stat-trio":
      return <StatTrio content={scene.content as StatTrioContent} theme={theme} />;
    case "two-column":
      return <TwoColumn content={scene.content as TwoColumnContent} theme={theme} />;
    case "architecture":
      return <Architecture content={scene.content as ArchitectureContent} theme={theme} />;
    case "bar-chart":
      return <BarChart content={scene.content as BarChartContent} theme={theme} />;
    case "timeline":
      return <Timeline content={scene.content as TimelineContent} theme={theme} />;
    case "team":
      return <Team content={scene.content as TeamContent} theme={theme} />;
    case "close":
      return <Close content={scene.content as CloseContent} theme={theme} />;
    default:
      throw new Error(`Unknown scene layout for minimal style: ${scene.layout}`);
  }
}
