import React from "react";
import { Composition } from "remotion";

import { PitchVideo } from "./PitchVideo";
import { ListingVideo } from "./listing/ListingVideo";
import type { ListingVideoProps } from "./listing/types";
import type { PitchVideoProps } from "./types";

// A deck's total duration/dimensions vary per render (driven by measured
// narration audio), so they're computed from the actual props at render
// time via calculateMetadata rather than fixed at registration.
export const RemotionRoot: React.FC = () => {
  return (
    <>
    <Composition
      id="PitchVideo"
      component={PitchVideo}
      durationInFrames={30 * 60}
      fps={30}
      width={1920}
      height={1080}
      defaultProps={{
        title: "Untitled deck",
        fps: 30,
        width: 1920,
        height: 1080,
        designTokens: {},
        scenes: [],
      } satisfies PitchVideoProps}
      calculateMetadata={async ({ props }) => {
        const p = props as PitchVideoProps;
        const totalFrames = p.scenes.reduce((sum, s) => sum + s.frameCount, 0);
        return {
          durationInFrames: Math.max(1, totalFrames),
          fps: p.fps || 30,
          width: p.width || 1920,
          height: p.height || 1080,
        };
      }}
    />
    <Composition
      id="ListingVideo"
      component={ListingVideo}
      durationInFrames={30 * 30}
      fps={30}
      width={1080}
      height={1920}
      defaultProps={{
        fps: 30,
        width: 1080,
        height: 1920,
        address: "123 Main St",
        priceText: "",
        listingType: "For Sale",
        features: [],
        agentName: "",
        agentPhone: "",
        brokerage: "",
        designTokens: null,
        photos: [],
        narrationPath: "narration.wav",
        musicPath: null,
        musicVolume: 0.14,
        timeline: {
          fps: 30, total_frames: 900, intro_frames: 75, outro_frames: 105, photos: [],
        },
      } satisfies ListingVideoProps}
      calculateMetadata={async ({ props }) => {
        const p = props as ListingVideoProps;
        return {
          durationInFrames: Math.max(1, p.timeline.total_frames),
          fps: p.fps || 30,
          width: p.width || 1080,
          height: p.height || 1920,
        };
      }}
    />
    </>
  );
};
