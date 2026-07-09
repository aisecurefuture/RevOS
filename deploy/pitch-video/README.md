# Pitch Video Studio — deployment

Deck Spec (JSON) → per-scene narration via the platform's existing XTTS-v2
voice engine → Remotion-rendered, brand-themed 1080p MP4.

Two workers split the job (both stages update the same `pitch_video_jobs` row):

| Stage | Queue | Runs on | Why |
|---|---|---|---|
| Narration audio | `avatar` | **existing avatar-worker** | it's the same XTTS backend Avatar Personas uses — no new TTS deploy |
| MP4 render | `pitch_video` | **new pitch-video-worker** | Node + Remotion + Chromium, kept out of the other images |

## ⚠️ Remotion licensing (before enabling)

Free for ≤3-employee companies; 4+ employees require a paid company license —
see `remotion/README.md`. Confirmed ≤3 employees as of 2026-07-07.

## One-time setup (on the server)

1. **Migrate** (adds `brands.design_tokens` + `pitch_video_jobs`):

   ```bash
   cd ~/RevOS && git pull
   docker compose exec api alembic upgrade head
   ```

2. **Pick the narration voice** (stock speakers bundled with XTTS-v2):

   ```bash
   docker compose exec avatar-worker /opt/xtts/bin/python -c "
   from TTS.api import TTS
   tts = TTS('tts_models/multilingual/multi-dataset/xtts_v2', progress_bar=False).to('cpu')
   print('\n'.join(tts.speakers))"
   ```

   "Ana Florence" is the validated default female voice.

3. **Configure** `.env`:

   ```
   PITCH_VIDEO_STUDIO_ENABLED=true
   PITCH_VIDEO_DEFAULT_VOICE=Ana Florence
   ```

4. **Enable the render worker**: uncomment the `pitch-video-worker` service in
   `docker-compose.yml`, then:

   ```bash
   docker compose up -d --build pitch-video-worker
   docker compose up -d --build api frontend avatar-worker worker
   docker compose logs --tail=5 pitch-video-worker   # should show the licensing notice
   ```

## CyberArmor.AI acceptance deck

Seed the brand's design tokens and print the ready-made 12-scene Deck Spec:

```bash
docker compose exec api python -m app.seed.pitch_video_demo
```

Paste the printed `deck_spec` into **Dashboard → Pitch Videos** (set
`"voice": "Ana Florence"` or leave empty to use the default), submit, and
poll. Audio generation runs on the avatar-worker (~15-60s/scene on CPU), then
the render (~2-5 min for a ~3 min deck).

## Manual fallback render (no queue involved)

If the workers are down and you need the MP4 *now*, render directly on any
machine with the repo + Node + the generated scene WAVs:

```bash
cd remotion && npm ci
REMOTION_PUBLIC_DIR=/path/to/scene-wavs \
npx remotion render src/index.ts PitchVideo out/cyberarmor.mp4 --props=/path/to/props.json
```

`props.json` format: `remotion/src/types.ts` (`PitchVideoProps`). The
worker logs the exact props path it used for any job, so a failed job's
props can be re-rendered by hand.

## Ops notes

- TTS audio is cached in storage at `pitch-videos/tts-cache/<sha256>.wav` —
  re-submitting a deck with unchanged narration+voice skips regeneration.
- Limits: `PITCH_VIDEO_MAX_SCENES` (default 20), render timeout 30 min,
  Remotion concurrency 1 (`PITCH_VIDEO_RENDER_CONCURRENCY`) — this box also
  runs XTTS/Wav2Lip, don't let renders starve them.
- The job row (`pitch_video_jobs`) is the source of truth; clients poll it.
  `progress_note` carries the per-scene progress string.
