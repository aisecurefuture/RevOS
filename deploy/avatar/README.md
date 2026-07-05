# Avatar worker (P3-M3) — self-hosted CPU voice + lip-sync

Generates talking-head avatar videos entirely on CPU, no paid APIs. The main
RevOS app enqueues a job on the `avatar` Celery queue; this worker (a separate
image carrying the ML stack) runs it: **XTTS-v2** clones the persona's voice
from their consented sample, then **Wav2Lip** lip-syncs that audio onto their
consented training video.

## Honest expectations

Generation is **minutes to hours** on CPU (measured ~1.7s of compute per output
frame — face detection dominates). Rough per-duration wait times the UI shows:

| Clip | ~Wait |
|---|---|
| 7s | ~6 min |
| 15s | ~13 min |
| 30s | ~26 min |
| 60s | ~50 min |
| 90s | ~75 min |
| 120s | ~100 min |

A GPU cuts this 10–30×; when one is available, swap the backend (the interface
is provider-agnostic) — no app changes needed.

## One-time setup

1. **Get the Wav2Lip checkpoint** (not baked into the image — large + licensed).
   Download `Wav2Lip-SD-GAN.pt` (or the standard `wav2lip_gan` checkpoint) from
   the Wav2Lip project, place it on the server, e.g. `/opt/revos/wav2lip.pt`.

2. **Build the image** (from repo root):
   ```bash
   docker build -f deploy/avatar/Dockerfile.avatar -t revos-avatar .
   ```
   First build is slow and large (multi-GB: torch ×2 venvs + models download on
   first job).

3. **Run the worker**, sharing the DB, Redis, and the storage volume with the
   main stack, and bind-mounting the checkpoint:
   ```bash
   docker run -d --name revos-avatar \
     --env-file .env \
     -e AVATAR_WAV2LIP_CHECKPOINT=/ckpt/wav2lip.pt \
     -v /opt/revos/wav2lip.pt:/ckpt/wav2lip.pt:ro \
     -v revos_storage:/app/storage \
     revos-avatar
   ```
   Or add it as a `avatar-worker` service in docker-compose (see the commented
   block in the repo's docker-compose.yml).

## Notes

- The worker runs `--concurrency=1`: each job pins the CPU, so one at a time.
- The checkpoint is a TorchScript mirror; `patch_wav2lip.py` (applied at build)
  adapts the stock `inference.py` to load it. If you use a different checkpoint
  format, re-check that patch.
- `AVATAR_BACKEND=local` is set in the image. The main API image leaves it
  unset (`none`) so it never attempts generation.
