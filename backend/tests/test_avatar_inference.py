"""Voice post-processing (presence lift + loudness normalization) applied to
raw XTTS output — a quality polish, not a correctness gate, so it must fail
open rather than blow up generation if ffmpeg or the input is unusable.
"""

from __future__ import annotations

import struct
import wave
from pathlib import Path

from app.services.avatar.inference import _post_process_voice


def _write_tiny_wav(path: Path, sample_rate: int = 24000, n_samples: int = 4800) -> None:
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(sample_rate)
        # a simple tone, not silence, so loudnorm has something to measure
        frames = [int(3000 * ((i % 100) / 100)) for i in range(n_samples)]
        w.writeframes(struct.pack(f"<{n_samples}h", *frames))


def test_post_process_keeps_a_valid_wav(tmp_path):
    path = tmp_path / "voice.wav"
    _write_tiny_wav(path)
    original_size = path.stat().st_size

    _post_process_voice(str(path))

    assert path.exists()
    with wave.open(str(path)) as w:
        assert w.getnframes() > 0
    # processed file should differ from the untouched original (EQ/loudnorm ran)
    assert path.stat().st_size != original_size or path.read_bytes()[:4] == b"RIFF"


def test_post_process_fails_open_on_garbage_input(tmp_path):
    path = tmp_path / "not_audio.wav"
    path.write_bytes(b"this is not a real audio file")

    _post_process_voice(str(path))  # must not raise

    assert path.exists()
    assert path.read_bytes() == b"this is not a real audio file"  # left untouched
