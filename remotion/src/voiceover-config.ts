// Central timing module. Every scene's duration is driven by its MEASURED
// narration audio duration — computed once, server-side, in Python
// (pitch_video_service._probe_duration_seconds via ffprobe) and passed in as
// frameStart/frameCount on each scene's props. Nothing on the Remotion side
// re-measures audio; @remotion/media-utils' getAudioDurationInSeconds is
// available if a scene ever needs to sanity-check at preview time, but the
// render itself must trust the manifest so Python and Node never disagree
// about how long a scene is.

export const FPS = 30;

export function secondsToFrames(seconds: number): number {
  return Math.max(1, Math.ceil(seconds * FPS));
}
