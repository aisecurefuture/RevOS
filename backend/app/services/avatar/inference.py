"""Avatar inference backends (Phase 3 M3, extended in Pitch Video Studio).

An ``InferenceBackend`` turns (script, voice, face video) into a lip-synced
talking-head video, in two stages:

    generate_voice(script, voice) -> audio.wav      (XTTS-v2)
    lip_sync(face_video, audio)   -> talking.mp4     (Wav2Lip)

``generate_voice`` takes its voice one of two ways — exactly one must be given:
  * ``voice_sample_path`` — zero-shot CLONING of a real person's recorded
    sample. This is consent-gated at the caller (Avatar Personas requires an
    active PersonaConsent before this path is ever reached).
  * ``speaker_name`` — one of XTTS-v2's built-in stock speakers, bundled with
    the model. No cloning, no consent surface — used for Pitch Video Studio's
    brand-narrator voice, where there's no consented persona to clone.

``LocalCpuBackend`` runs the exact stack validated on the CPU box, driving two
isolated virtualenvs via subprocess (they have conflicting deps — librosa/numpy
— so they can't share one env). ``StubBackend`` writes tiny placeholder files so
the whole job lifecycle is exercisable in tests and demos without the ML stack.

Both stages are blocking and long (minutes); callers run them off the event
loop (the avatar worker calls them from a thread).
"""

from __future__ import annotations

import logging
import shutil
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


def _post_process_voice(path: str) -> None:
    """Slight presence lift + loudness normalization on the raw XTTS output.

    XTTS-v2's native output measures somewhat more attenuated in the 3-5kHz
    range than typical recorded reference speech; a small high-shelf boost
    plus consistent loudness makes the clone read less muffled and more
    uniform across generations. Fails open (leaves the raw file untouched) if
    ffmpeg is unavailable or the filter errors — this is a quality polish, not
    a correctness gate.
    """
    if not shutil.which("ffmpeg"):
        return
    fixed = f"{path}.fixed.wav"
    result = subprocess.run(  # noqa: S603
        ["ffmpeg", "-y", "-i", path, "-af",  # noqa: S607
         "highshelf=f=3000:g=2.5,loudnorm=I=-16:TP=-1.5:LRA=11", fixed],
        capture_output=True, timeout=120, check=False,
    )
    if result.returncode == 0 and Path(fixed).exists():
        Path(fixed).replace(path)
    else:
        logger.warning(
            "Voice post-process failed, using raw XTTS output as-is: %s",
            result.stderr.decode(errors="replace")[-500:],
        )
        Path(fixed).unlink(missing_ok=True)


class InferenceBackend(Protocol):
    name: str

    @property
    def available(self) -> bool: ...

    def generate_voice(
        self, *, script: str, out_path: str,
        voice_sample_path: str | None = None, speaker_name: str | None = None,
    ) -> None: ...

    def lip_sync(self, *, face_video_path: str, audio_path: str, out_path: str) -> None: ...


# ---------------------------------------------------------------------------
# Local CPU backend — the validated XTTS + Wav2Lip subprocess pipeline
# ---------------------------------------------------------------------------

def chunk_narration(text: str, max_chars: int = 220) -> list[str]:
    """Split narration into chunks XTTS can always synthesize.

    XTTS hard-fails past 400 tokens per generation. Its own sentence splitter
    handles normal prose, but text with no sentence punctuation (e.g. a
    deterministic PPTX draft of slide bullets) arrives as one giant chunk and
    crashes. Split on sentence enders first, then hard-wrap any still-long
    piece at word boundaries. ~220 chars stays comfortably under the token
    limit for English.

    NOTE: the same algorithm is inlined in _XTTS_RUNNER below (the runner
    executes in the isolated XTTS venv and can't import app code) — keep the
    two in sync.
    """
    import re as _re

    sentences = [s.strip() for s in _re.split(r"(?<=[.!?…])\s+", text.strip()) if s.strip()]
    chunks: list[str] = []
    for sentence in sentences:
        if len(sentence) <= max_chars:
            if chunks and len(chunks[-1]) + 1 + len(sentence) <= max_chars:
                chunks[-1] = f"{chunks[-1]} {sentence}"
            else:
                chunks.append(sentence)
            continue
        words, current = sentence.split(), ""
        for word in words:
            if current and len(current) + 1 + len(word) > max_chars:
                chunks.append(current)
                current = word
            else:
                current = f"{current} {word}".strip()
        if current:
            chunks.append(current)
    return chunks or [text[:max_chars]]


# Standalone script run by the XTTS venv's python. Kept as a string so the
# backend is self-contained (no extra file to ship/track); written to a temp
# file per call. Takes text/out paths plus EITHER --speaker-wav (cloning) OR
# --speaker-name (a built-in stock voice, no cloning). Long text is chunked
# (same algorithm as chunk_narration above) and the WAVs are concatenated —
# XTTS crashes outright past 400 tokens in a single unbreakable chunk.
_XTTS_RUNNER = r'''
import argparse
import re
import wave
from TTS.api import TTS

p = argparse.ArgumentParser()
p.add_argument("text_path")
p.add_argument("out_path")
p.add_argument("--speaker-wav", default=None)
p.add_argument("--speaker-name", default=None)
args = p.parse_args()

with open(args.text_path, "r", encoding="utf-8") as f:
    text = f.read().strip()

MAX_CHARS = 220  # keep in sync with inference.chunk_narration

def chunk_narration(text, max_chars=MAX_CHARS):
    sentences = [s.strip() for s in re.split(r"(?<=[.!?…])\s+", text.strip()) if s.strip()]
    chunks = []
    for sentence in sentences:
        if len(sentence) <= max_chars:
            if chunks and len(chunks[-1]) + 1 + len(sentence) <= max_chars:
                chunks[-1] = chunks[-1] + " " + sentence
            else:
                chunks.append(sentence)
            continue
        words, current = sentence.split(), ""
        for word in words:
            if current and len(current) + 1 + len(word) > max_chars:
                chunks.append(current)
                current = word
            else:
                current = (current + " " + word).strip()
        if current:
            chunks.append(current)
    return chunks or [text[:max_chars]]

tts = TTS("tts_models/multilingual/multi-dataset/xtts_v2", progress_bar=False).to("cpu")

def synth(chunk_text, path):
    if args.speaker_wav:
        tts.tts_to_file(text=chunk_text, speaker_wav=args.speaker_wav, language="en", file_path=path)
    else:
        tts.tts_to_file(text=chunk_text, speaker=args.speaker_name, language="en", file_path=path)

chunks = chunk_narration(text)
if len(chunks) == 1:
    synth(chunks[0], args.out_path)
else:
    parts = []
    for i, chunk in enumerate(chunks):
        part = f"{args.out_path}.part{i}.wav"
        synth(chunk, part)
        parts.append(part)
    with wave.open(args.out_path, "wb") as out:
        for i, part in enumerate(parts):
            with wave.open(part, "rb") as src:
                if i == 0:
                    out.setparams(src.getparams())
                out.writeframes(src.readframes(src.getnframes()))
'''

# Diagnostic script — lists the model's built-in stock speaker names. Run this
# on the server (see deploy/pitch-video/README.md) to get the REAL list before
# picking PITCH_VIDEO_DEFAULT_VOICE; XTTS-v2's bundled speaker set isn't
# guaranteed stable across model versions, so nothing here hardcodes a name.
_XTTS_LIST_SPEAKERS = r'''
from TTS.api import TTS

tts = TTS("tts_models/multilingual/multi-dataset/xtts_v2", progress_bar=False).to("cpu")
for name in (tts.speakers or []):
    print(name)
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

    def generate_voice(
        self, *, script: str, out_path: str,
        voice_sample_path: str | None = None, speaker_name: str | None = None,
    ) -> None:
        if bool(voice_sample_path) == bool(speaker_name):
            raise BackendError("generate_voice needs exactly one of voice_sample_path or speaker_name.")
        with tempfile.TemporaryDirectory() as tmp:
            runner = Path(tmp) / "xtts_runner.py"
            runner.write_text(_XTTS_RUNNER, encoding="utf-8")
            text_file = Path(tmp) / "script.txt"
            text_file.write_text(script, encoding="utf-8")
            cmd = [self.xtts_python, str(runner), str(text_file), out_path]
            cmd += ["--speaker-wav", voice_sample_path] if voice_sample_path else ["--speaker-name", speaker_name]
            self._run(cmd, context="voice")
        if not Path(out_path).exists():
            raise BackendError("Voice generation produced no output.")
        _post_process_voice(out_path)

    def list_stock_speakers(self) -> list[str]:
        """Diagnostic: enumerate XTTS-v2's built-in stock speaker names on
        this box. Not used by generation itself — run once to pick a value
        for PITCH_VIDEO_DEFAULT_VOICE."""
        with tempfile.TemporaryDirectory() as tmp:
            runner = Path(tmp) / "list_speakers.py"
            runner.write_text(_XTTS_LIST_SPEAKERS, encoding="utf-8")
            proc = subprocess.run(
                [self.xtts_python, str(runner)], capture_output=True, text=True, timeout=self.timeout,
            )
        if proc.returncode != 0:
            raise BackendError(f"Could not list speakers: {(proc.stderr or proc.stdout)[-1500:]}")
        return [line.strip() for line in proc.stdout.splitlines() if line.strip()]

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

    def generate_voice(
        self, *, script: str, out_path: str,
        voice_sample_path: str | None = None, speaker_name: str | None = None,
    ) -> None:
        # A real (if tiny) valid WAV — silence, roughly 1s per 20 chars of
        # script — so anything that probes duration (e.g. Pitch Video Studio's
        # frame timing) gets a real, ffprobe-readable file, not just bytes
        # that happen to satisfy "the file exists".
        import wave

        seconds = max(1.0, len(script) / 20.0)
        framerate = 24000
        with wave.open(out_path, "wb") as w:
            w.setnchannels(1)
            w.setsampwidth(2)
            w.setframerate(framerate)
            w.writeframes(b"\x00\x00" * int(framerate * seconds))

    def list_stock_speakers(self) -> list[str]:
        return ["stub-speaker-1", "stub-speaker-2"]

    def lip_sync(self, *, face_video_path: str, audio_path: str, out_path: str) -> None:
        Path(out_path).write_bytes(b"\x00\x00\x00\x18ftypmp42stub-video")


def get_backend() -> InferenceBackend | None:
    if settings.avatar_backend == "local":
        return LocalCpuBackend()
    if settings.avatar_backend == "stub":
        return StubBackend()
    return None
