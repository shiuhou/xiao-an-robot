"""Audio input helpers for file-first ASR/VAD smoke tests."""

from __future__ import annotations

from pathlib import Path
import wave


def load_wav_audio_file(audio_path: str) -> dict:
    """Load a local PCM WAV file into the lightweight audio clip contract."""

    path = Path(audio_path).expanduser()
    if not path.exists():
        raise FileNotFoundError(f"Audio file does not exist: {audio_path}")
    if not path.is_file():
        raise RuntimeError(f"Audio path is not a file: {audio_path}")

    try:
        with wave.open(str(path), "rb") as wav:
            channels = wav.getnchannels()
            sample_rate = wav.getframerate()
            sample_width = wav.getsampwidth()
            frame_count = wav.getnframes()
            pcm_bytes = wav.readframes(frame_count)
    except wave.Error as exc:
        raise RuntimeError(f"Failed to read WAV audio file {audio_path!r}: {exc}") from exc

    duration_ms = int(round((frame_count / sample_rate) * 1000)) if sample_rate else 0
    return {
        "source": "audio_file",
        "audio_path": str(path),
        "sample_rate": sample_rate,
        "duration_ms": duration_ms,
        "channels": channels,
        "sample_width": sample_width,
        "frame_count": frame_count,
        "pcm_bytes": pcm_bytes,
    }
