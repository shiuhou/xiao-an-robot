"""Raw PCM microphone diagnostics for ESP32 /audio bring-up."""

from __future__ import annotations

import argparse
import json
import math
import struct
import sys
import wave
from pathlib import Path
from typing import Sequence

PCM_FORMAT = "pcm_s16le"
DEFAULT_SAMPLE_RATE = 16000
DEFAULT_CHANNELS = 1
S16_FULL_SCALE = 32768.0


def _dbfs(amplitude: float) -> float | None:
    if amplitude <= 0:
        return None
    return round(20.0 * math.log10(amplitude / S16_FULL_SCALE), 3)


def _read_samples_s16le(pcm_bytes: bytes) -> tuple[int, ...]:
    if len(pcm_bytes) % 2:
        raise ValueError("pcm_s16le input must contain an even number of bytes")
    if not pcm_bytes:
        return ()
    return struct.unpack(f"<{len(pcm_bytes) // 2}h", pcm_bytes)


def pcm_s16le_stats(
    pcm_bytes: bytes,
    *,
    sample_rate: int = DEFAULT_SAMPLE_RATE,
    channels: int = DEFAULT_CHANNELS,
) -> dict:
    """Return level and integrity stats for signed 16-bit little-endian PCM."""

    if sample_rate <= 0:
        raise ValueError("sample_rate must be positive")
    if channels <= 0:
        raise ValueError("channels must be positive")

    samples = _read_samples_s16le(pcm_bytes)
    sample_count = len(samples)
    frame_count = sample_count / channels
    duration_ms = round((frame_count / sample_rate) * 1000.0, 3) if sample_count else 0.0

    if not samples:
        return {
            "format": PCM_FORMAT,
            "sample_rate": sample_rate,
            "channels": channels,
            "sample_count": 0,
            "frame_count": 0,
            "duration_ms": 0.0,
            "rms": 0.0,
            "rms_dbfs": None,
            "peak": 0,
            "peak_dbfs": None,
            "clipping_samples": 0,
            "clipping_percent": 0.0,
            "dc_offset": 0.0,
            "dc_offset_percent": 0.0,
        }

    square_sum = sum(float(sample) * float(sample) for sample in samples)
    rms = math.sqrt(square_sum / sample_count)
    peak = max(abs(sample) for sample in samples)
    clipping_samples = sum(1 for sample in samples if sample <= -32768 or sample >= 32767)
    dc_offset = sum(samples) / sample_count

    return {
        "format": PCM_FORMAT,
        "sample_rate": sample_rate,
        "channels": channels,
        "sample_count": sample_count,
        "frame_count": int(frame_count) if frame_count.is_integer() else frame_count,
        "duration_ms": duration_ms,
        "rms": round(rms, 3),
        "rms_dbfs": _dbfs(rms),
        "peak": peak,
        "peak_dbfs": _dbfs(float(peak)),
        "clipping_samples": clipping_samples,
        "clipping_percent": round((clipping_samples / sample_count) * 100.0, 3),
        "dc_offset": round(dc_offset, 3),
        "dc_offset_percent": round((dc_offset / S16_FULL_SCALE) * 100.0, 3),
    }


def write_pcm_s16le_wav(
    pcm_bytes: bytes,
    wav_path: Path | str,
    *,
    sample_rate: int = DEFAULT_SAMPLE_RATE,
    channels: int = DEFAULT_CHANNELS,
) -> Path:
    """Write raw pcm_s16le bytes as a WAV file and return the output path."""

    _read_samples_s16le(pcm_bytes)
    if sample_rate <= 0:
        raise ValueError("sample_rate must be positive")
    if channels <= 0:
        raise ValueError("channels must be positive")

    output = Path(wav_path)
    output.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(output), "wb") as wav:
        wav.setnchannels(channels)
        wav.setsampwidth(2)
        wav.setframerate(sample_rate)
        wav.writeframes(pcm_bytes)
    return output


def diagnose_pcm_file(
    pcm_path: Path | str,
    *,
    wav_path: Path | str | None = None,
    report_path: Path | str | None = None,
    sample_rate: int = DEFAULT_SAMPLE_RATE,
    channels: int = DEFAULT_CHANNELS,
) -> dict:
    """Analyze a raw PCM file, optionally exporting WAV and JSON report files."""

    source = Path(pcm_path)
    pcm_bytes = source.read_bytes()
    report = pcm_s16le_stats(pcm_bytes, sample_rate=sample_rate, channels=channels)
    report["source_pcm"] = str(source)

    if wav_path is not None:
        output_wav = write_pcm_s16le_wav(
            pcm_bytes,
            wav_path,
            sample_rate=sample_rate,
            channels=channels,
        )
        report["wav_path"] = str(output_wav)

    if report_path is not None:
        output_report = Path(report_path)
        output_report.parent.mkdir(parents=True, exist_ok=True)
        output_report.write_text(
            json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True),
            encoding="utf-8",
        )
        report["report_path"] = str(output_report)

    return report


def _default_wav_path(pcm_path: Path) -> Path:
    return pcm_path.with_suffix(".wav")


def _default_report_path(pcm_path: Path) -> Path:
    return pcm_path.with_suffix(".audio_stats.json")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Inspect raw INMP441 pcm_s16le audio and optionally export WAV.",
    )
    parser.add_argument(
        "pcm_path",
        nargs="?",
        default="runtime/latest_audio.pcm",
        help="Raw pcm_s16le input file. Defaults to runtime/latest_audio.pcm.",
    )
    parser.add_argument("--sample-rate", type=int, default=DEFAULT_SAMPLE_RATE)
    parser.add_argument("--channels", type=int, default=DEFAULT_CHANNELS)
    parser.add_argument(
        "--wav-out",
        default=None,
        help="WAV output path. Defaults to the PCM path with .wav suffix when --no-wav is not set.",
    )
    parser.add_argument(
        "--report-out",
        default=None,
        help="JSON report path. Defaults to the PCM path with .audio_stats.json suffix.",
    )
    parser.add_argument("--no-wav", action="store_true", help="Only print/report stats; do not write a WAV.")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    pcm_path = Path(args.pcm_path)
    wav_path = None if args.no_wav else Path(args.wav_out) if args.wav_out else _default_wav_path(pcm_path)
    report_path = Path(args.report_out) if args.report_out else _default_report_path(pcm_path)

    try:
        report = diagnose_pcm_file(
            pcm_path,
            wav_path=wav_path,
            report_path=report_path,
            sample_rate=args.sample_rate,
            channels=args.channels,
        )
    except (OSError, ValueError) as exc:
        print(f"audio diagnostic failed: {exc}", file=sys.stderr)
        return 2

    print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
