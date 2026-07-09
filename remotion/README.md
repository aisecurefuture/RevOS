# RevOS Pitch Video Studio — Remotion project

Turns a validated Deck Spec + a Brand's `design_tokens` into a narrated,
brand-themed MP4. This directory is the **render half** of the feature; the
**orchestration half** (Deck Spec validation, narration TTS, job lifecycle)
lives in `backend/app/services/pitch_video_service.py`.

## ⚠️ Licensing — read before enabling in production

Remotion is **not** plain MIT software. Under the Remotion license:

- **Free** for individuals, non-profits, and for-profit companies with
  **3 or fewer employees**.
- **4 or more employees** → a paid company license is required
  (https://www.remotion.dev/license).

**Status for this repo:** confirmed ≤3 employees as of **2026-07-07** — the
free tier applies. If the operating company grows to 4+ employees, purchase a
company license **before** the next render. The `pitch-video-worker` logs this
notice at startup as a standing reminder.

## How a render works

1. `pitch_video_service.run_audio_generation` (avatar-worker) generates one
   WAV per scene via XTTS-v2 — the same self-hosted TTS Avatar Personas uses —
   using a built-in **stock speaker** (no voice cloning). Audio is cached in
   storage by `sha256(voice + narration text)`. Each clip's duration is
   measured with ffprobe and converted to `frameCount` (30fps, rounded up).
2. `pitch_video_service.run_render` (pitch-video-worker) materializes the
   cached WAVs into a temp dir, writes a `props.json`, and shells out to
   `npx remotion render` with `REMOTION_PUBLIC_DIR` pointing at that temp dir
   — scenes reference audio via `staticFile(<filename>)`.
3. The MP4 goes back into tenant storage; clients download through the
   authenticated `/api/pitch-videos/{id}/video` endpoint.

**All timing lives in the manifest** built in step 1 (`voiceover-config.ts`
documents this contract). Nothing on the Node side re-measures audio, so
Python and the composition can never disagree about scene durations.

## Scene library

`hero`, `statement` (plain or equation), `stat-trio`, `two-column`,
`architecture` (layered bands), `bar-chart` (stacked, with optional
"illustrative" note), `timeline`, `team`, `close`. Every component is themed
entirely from `Brand.design_tokens` — **no hardcoded colors or fonts**; a
brand with no tokens gets a validated, accessible neutral default
(`src/theme.ts`).

## Local development

```bash
cd remotion
npm install
npm run typecheck

# Live-preview the composition with sample props:
npx remotion studio src/index.ts

# Render manually (the same command the worker runs):
REMOTION_PUBLIC_DIR=/path/to/dir-with-scene-wavs \
npx remotion render src/index.ts PitchVideo out/output.mp4 --props=/path/to/props.json
```

`props.json` shape: see `src/types.ts` (`PitchVideoProps`) — it mirrors
`backend/app/schemas/pitch_video.py` exactly; change them together.

## Picking a narration voice

Stock speaker names are bundled with the XTTS-v2 model. List them on any
machine with the XTTS venv (e.g. the avatar-worker):

```bash
docker compose exec avatar-worker /opt/xtts/bin/python -c "
from TTS.api import TTS
tts = TTS('tts_models/multilingual/multi-dataset/xtts_v2', progress_bar=False).to('cpu')
print('\n'.join(tts.speakers))"
```

Set the winner as `PITCH_VIDEO_DEFAULT_VOICE` in `.env`, or per-deck via the
Deck Spec's `voice` field. ("Ana Florence" is a good default female voice;
"Damien Black" a good male one.)
