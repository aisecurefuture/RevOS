"""Avatar inference backends (Phase 3 M3).

An ``InferenceBackend`` turns (script, voice sample, face video) into a
lip-synced talking-head video, in two stages:

    generate_voice(script, voice_sample) -> audio.wav      (XTTS-v2, cloned)
    lip_sync(face_video, audio)          -> talking.mp4     (Wav2Lip)

``LocalCpuBackend`` runs the exact stack validated on the CPU box, driving two
isolated virtualenvs via subprocess (they have conflicting deps — librosa/numpy
— so they can't share one env). ``StubBackend`` writes tiny placeholder files so
the whole job lifecycle is exercisable in tests and demos without the ML stack.

Both stages are blocking and long (minutes); callers run them off the event
loop (the avatar worker calls them from a thread).
"""

from __future__ import annotations

import logging
import subprocess
import tempfile
from pathlib import Path
from typing import Protocol

from app.config import settings
from app.core.exceptions import RevOSError

logger = logging.getLogger("revos.avatar.inference")


class BackendError(RevOSError):
    code = "avatar_backend_error"
    status_code = 502


class InferenceBackend(Protocol):
    name: str

    @property
    def available(self) -> bool: ...

    def generate_voice(self, *, script: str, voice_sample_path: str, out_path: str) -> None: ...

    def lip_sync(self, *, face_video_path: str, audio_path: str, out_path: str) -> None: ...


# ---------------------------------------------------------------------------
# Local CPU backend — the validated XTTS + Wav2Lip subprocess pipeline
# ---------------------------------------------------------------------------

# Standalone script run by the XTTS venv's python. Kept as a string so the
# backend is self-contained (no extra file to ship/track); written to a temp
# file per call. Reads text/speaker/out from argv.
_XTTS_RUNNER = r'''
import sys
from TTS.api import TTS

text_path, speaker_wav, out_path = sys.argv[1], sys.argv[2], sys.argv[3]
with open(text_path, "r", encoding="utf-8") as f:
    text = f.read().strip()

tts = TTS("tts_models/multilingual/multi-dataset/xtts_v2", progress_bar=False).to("cpu")
tts.tts_to_file(text=text, speaker_wav=speaker_wav, language="en", file_path=out_path)
'''


class LocalCpuBackend:
    name = "local"

    def __init__(self) -> None:
        self.xtts_python = settings.avatar_xtts_python
        self.wav2lip_dir = settings.avatar_wav2lip_dir
        self.wav2lip_python = settings.avatar_wav2lip_python
        self.checkpoint = settings.avatar_wav2lip_checkpoint
        self.timeout = settings.avatar_job_timeout_seconds

    @property
    def available(self) -> bool:
        paths = [self.xtts_python, self.wav2lip_python, self.wav2lip_dir, self.checkpoint]
        return all(paths) and all(Path(p).exists() for p in paths)

    def generate_voice(self, *, script: str, voice_sample_path: str, out_path: str) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            runner = Path(tmp) / "xtts_runner.py"
            runner.write_text(_XTTS_RUNNER, encoding="utf-8")
            text_file = Path(tmp) / "script.txt"
            text_file.write_text(script, encoding="utf-8")
            self._run(
                [self.xtts_python, str(runner), str(text_file), voice_sample_path, out_path],
                context="voice",
            )
        if not Path(out_path).exists():
            raise BackendError("Voice generation produced no output.")

    def lip_sync(self, *, face_video_path: str, audio_path: str, out_path: str) -> None:
        self._run(
            [
                self.wav2lip_python, "inference.py",
                "--checkpoint_path", self.checkpoint,
                "--face", face_video_path,
                "--audio", audio_path,
                "--outfile", out_path,
            ],
            context="lip_sync",
            cwd=self.wav2lip_dir,
        )
        if not Path(out_path).exists():
            raise BackendError("Lip-sync produced no output.")

    def _run(self, cmd: list[str], *, context: str, cwd: str | None = None) -> None:
        logger.info("avatar[%s]: %s", context, " ".join(cmd))
        try:
            proc = subprocess.run(
                cmd, cwd=cwd, capture_output=True, text=True, timeout=self.timeout,
            )
        except subprocess.TimeoutExpired as exc:
            raise BackendError(f"{context} timed out after {self.timeout}s.") from exc
        if proc.returncode != 0:
            tail = (proc.stderr or proc.stdout or "")[-1500:]
            logger.error("avatar[%s] failed (%s): %s", context, proc.returncode, tail)
            raise BackendError(f"{context} failed: {tail}")


# ---------------------------------------------------------------------------
# Stub backend — tests / demo (no ML stack required)
# ---------------------------------------------------------------------------

class StubBackend:
    name = "stub"
    available = True

    def generate_voice(self, *, script: str, voice_sample_path: str, out_path: str) -> None:
        # Minimal valid-ish WAV header + silence marker; enough to exercise the flow.
        Path(out_path).write_bytes(b"RIFF\x00\x00\x00\x00WAVEstub-audio")

    def lip_sync(self, *, face_video_path: str, audio_path: str, out_path: str) -> None:
        Path(out_path).write_bytes(b"\x00\x00\x00\x18ftypmp42stub-video")


def get_backend() -> InferenceBackend | None:
    if settings.avatar_backend == "local":
        return LocalCpuBackend()
    if settings.avatar_backend == "stub":
        return StubBackend()
    return None
