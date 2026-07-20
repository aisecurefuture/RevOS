// Mirrors the props JSON built by app/services/listing_video_service.py
// (run_render). Field names match the Python side verbatim — this file is
// the other half of that contract.

import type { DesignTokens } from "../types";

export interface PhotoSlot {
  index: number;
  frame_start: number;
  frame_count: number;
}

export interface ListingTimeline {
  fps: number;
  total_frames: number;
  intro_frames: number;
  outro_frames: number;
  photos: PhotoSlot[];
}

export interface ListingVideoProps extends Record<string, unknown> {
  fps: number;
  width: number;
  height: number;
  address: string;
  priceText: string;
  listingType: string;
  beds?: number | null;
  baths?: number | null;
  sqft?: number | null;
  features: string[];
  agentName: string;
  agentPhone: string;
  brokerage: string;
  designTokens: DesignTokens | null;
  photos: string[];          // filenames resolved via staticFile()
  narrationPath: string;     // filename resolved via staticFile()
  musicPath?: string | null; // filename resolved via staticFile()
  musicVolume?: number;
  timeline: ListingTimeline;
}
