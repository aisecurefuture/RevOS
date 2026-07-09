import { Config } from "@remotion/cli/config";

Config.setVideoImageFormat("jpeg");
Config.setOverwriteOutput(true);

// Each render's scene audio lives in a fresh temp directory (materialized
// from storage by pitch_video_service.run_render), so the "public dir" —
// Remotion's servable-static-asset root — must be set per-invocation via env
// var rather than a fixed path. Scenes reference audio via staticFile(),
// relative to whatever this resolves to.
if (process.env.REMOTION_PUBLIC_DIR) {
  Config.setPublicDir(process.env.REMOTION_PUBLIC_DIR);
}
