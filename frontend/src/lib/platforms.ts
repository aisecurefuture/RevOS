// Display labels for social platforms. The INTERNAL identifier stays
// "twitter" everywhere (DB enum value, env vars, OAuth routes) — only the
// user-facing label is "X". Keep this the single source of label truth.

export const PLATFORM_LABELS: Record<string, string> = {
  linkedin: "LinkedIn",
  instagram: "Instagram",
  facebook: "Facebook",
  twitter: "X",
  youtube: "YouTube",
  youtube_short: "YouTube Short",
  tiktok: "TikTok",
  threads: "Threads",
};

export function platformLabel(platform: string): string {
  return PLATFORM_LABELS[platform] ?? platform.replace(/_/g, " ");
}
