"""Speech-window extraction helpers for file-first ASR."""

from __future__ import annotations

from pathlib import Path
import math
import struct
import wave


def trim_wav_to_speech(
    source_path: str | Path,
    trimmed_path: str | Path,
    *,
    threshold: float = 0.01,
    frame_ms: int = 20,
    padding_ms: int = 200,
) -> dict:
    """Trim a PCM WAV to the first/last energy frames above threshold."""

    source = Path(source_path)
    target = Path(trimmed_path)
    pcm, sample_rate, channels, sample_width = _read_pcm_wav(source)
    if channels != 1 or sample_width != 2:
        raise RuntimeError(
            "Speech trimming currently supports 16-bit mono PCM WAV only. "
            f"Got channels={channels}, sample_width={sample_width}."
        )

    samples = _unpack_s16le(pcm)
    frame_samples = max(1, int(sample_rate * frame_ms / 1000))
    speech_frames = [
        index
        for index, start in enumerate(range(0, len(samples), frame_samples))
        if _rms_energy(samples[start:start + frame_samples]) >= threshold
    ]

    if not speech_frames:
        return {
            "speech_detected": False,
            "source_path": str(source),
            "trimmed_path": str(target),
            "sample_rate": sample_rate,
            "channels": channels,
            "start_ms": None,
            "end_ms": None,
            "duration_ms": 0,
        }

    padding_samples = int(sample_rate * padding_ms / 1000)
    start_sample = max(0, speech_frames[0] * frame_samples - padding_samples)
    end_sample = min(
        len(samples),
        (speech_frames[-1] + 1) * frame_samples + padding_samples,
    )
    trimmed_samples = samples[start_sample:end_sample]
    target.parent.mkdir(parents=True, exist_ok=True)
    _write_pcm_wav(target, trimmed_samples, sample_rate=sample_rate)

    start_ms = int(round(start_sample * 1000 / sample_rate))
    end_ms = int(round(end_sample * 1000 / sample_rate))
    return {
        "speech_detected": True,
        "source_path": str(source),
        "trimmed_path": str(target),
        "sample_rate": sample_rate,
        "channels": channels,
        "start_ms": start_ms,
        "end_ms": end_ms,
        "duration_ms": end_ms - start_ms,
        "threshold": threshold,
        "frame_ms": frame_ms,
        "padding_ms": padding_ms,
    }


def _read_pcm_wav(path: Path) -> tuple[bytes, int, int, int]:
    try:
        with wave.open(str(path), "rb") as wav:
            channels = wav.getnchannels()
            sample_rate = wav.getframerate()
            sample_width = wav.getsampwidth()
            frame_count = wav.getnframes()
            pcm = wav.readframes(frame_count)
    except wave.Error as exc:
        raise RuntimeError(f"Failed to read WAV audio file {path!r}: {exc}") from exc
    return pcm, sample_rate, channels, sample_width


def _unpack_s16le(pcm: bytes) -> tuple[int, ...]:
    usable = len(pcm) - (len(pcm) % 2)
    if usable <= 0:
        return ()
    return struct.unpack("<" + "h" * (usable // 2), pcm[:usable])


def _rms_energy(samples: tuple[int, ...]) -> float:
    if not samples:
        return 0.0
    mean_square = sum((sample / 32768.0) ** 2 for sample in samples) / len(samples)
    return math.sqrt(mean_square)


def _write_pcm_wav(path: Path, samples: tuple[int, ...], *, sample_rate: int) -> None:
    with wave.open(str(path), "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(sample_rate)
        wav.writeframes(struct.pack("<" + "h" * len(samples), *samples))
