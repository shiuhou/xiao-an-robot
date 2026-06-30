"""Fixed-window ASR demo built on the robot /audio PCM stream."""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
import time
from pathlib import Path
from typing import Sequence

from base_station.monitor.asr_runtime import run_once
from base_station.perception.audio_diagnostics import pcm_s16le_stats, write_pcm_s16le_wav


class TailEnergyReader:
    """Read recent PCM tail energy from the rolling latest_audio.pcm file."""

    def __init__(self, pcm_path: str | Path, *, sample_rate: int = 16000, tail_ms: int = 200) -> None:
        self.pcm_path = Path(pcm_path)
        self.sample_rate = sample_rate
        self.tail_ms = tail_ms

    def read_tail_stats(self) -> dict | None:
        try:
            pcm = self.pcm_path.read_bytes()
        except OSError:
            return None

        tail_bytes = max(2, int(self.sample_rate * self.tail_ms / 1000) * 2)
        tail = pcm[-tail_bytes:]
        if len(tail) < 2:
            return None
        if len(tail) % 2:
            tail = tail[1:]
        return pcm_s16le_stats(tail, sample_rate=self.sample_rate, channels=1)


class UtteranceDetector:
    """Small state machine for utterance start/end based on tail RMS."""

    def __init__(
        self,
        *,
        trigger_rms_dbfs: float = -42.0,
        release_rms_dbfs: float = -48.0,
        silence_ms: int = 1000,
        min_speech_ms: int = 400,
        cooldown_ms: int = 1000,
    ) -> None:
        self.trigger_rms_dbfs = trigger_rms_dbfs
        self.release_rms_dbfs = release_rms_dbfs
        self.silence_ms = silence_ms
        self.min_speech_ms = min_speech_ms
        self.cooldown_ms = cooldown_ms
        self.state = "idle"
        self.start_ms: int | None = None
        self.last_voice_ms: int | None = None
        self.cooldown_until_ms = 0

    def update(self, *, now_ms: int, rms_dbfs: float | None) -> dict | None:
        if rms_dbfs is None:
            return None
        if now_ms < self.cooldown_until_ms:
            return None

        if self.state == "idle":
            if rms_dbfs >= self.trigger_rms_dbfs:
                self.state = "speaking"
                self.start_ms = now_ms
                self.last_voice_ms = now_ms
            return None

        if rms_dbfs >= self.release_rms_dbfs:
            self.last_voice_ms = now_ms
            return None

        if self.last_voice_ms is None or self.start_ms is None:
            self._reset()
            return None

        if now_ms - self.last_voice_ms < self.silence_ms:
            return None

        duration_ms = now_ms - self.start_ms
        if duration_ms < self.min_speech_ms:
            self._reset()
            return None

        event = {
            "start_ms": self.start_ms,
            "end_ms": now_ms,
            "duration_ms": duration_ms,
        }
        self._reset()
        self.cooldown_until_ms = now_ms + self.cooldown_ms
        return event

    def _reset(self) -> None:
        self.state = "idle"
        self.start_ms = None
        self.last_voice_ms = None


def export_latest_pcm_to_wav(
    pcm_path: str | Path,
    wav_path: str | Path,
    *,
    sample_rate: int = 16000,
) -> dict:
    pcm = Path(pcm_path).read_bytes()
    write_pcm_s16le_wav(pcm, wav_path, sample_rate=sample_rate, channels=1)
    stats = pcm_s16le_stats(pcm, sample_rate=sample_rate, channels=1)
    stats["wav_path"] = str(wav_path)
    stats["source_pcm"] = str(pcm_path)
    return stats


async def listen_and_transcribe(args: argparse.Namespace) -> int:
    reader = TailEnergyReader(args.audio_pcm, sample_rate=args.sample_rate, tail_ms=args.tail_ms)
    detector = UtteranceDetector(
        trigger_rms_dbfs=args.trigger_rms_dbfs,
        release_rms_dbfs=args.release_rms_dbfs,
        silence_ms=args.silence_ms,
        min_speech_ms=args.min_speech_ms,
        cooldown_ms=args.cooldown_ms,
    )
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    print(
        "fixed_window_asr_demo listening "
        f"pcm={args.audio_pcm} trigger={args.trigger_rms_dbfs}dB release={args.release_rms_dbfs}dB",
        flush=True,
    )

    start = time.monotonic()
    utterances = 0
    while args.max_seconds <= 0 or time.monotonic() - start < args.max_seconds:
        stats = reader.read_tail_stats()
        now_ms = int(time.monotonic() * 1000)
        rms_dbfs = stats.get("rms_dbfs") if stats else None
        peak_dbfs = stats.get("peak_dbfs") if stats else None
        event = detector.update(now_ms=now_ms, rms_dbfs=rms_dbfs)

        if args.verbose and stats:
            print(
                f"tail rms={_fmt_db(rms_dbfs)} peak={_fmt_db(peak_dbfs)} state={detector.state}",
                flush=True,
            )

        if event is not None:
            utterances += 1
            stamp = time.strftime("%Y%m%d_%H%M%S")
            wav_path = output_dir / f"fixed_window_utterance_{stamp}_{utterances}.wav"
            trim_path = output_dir / f"fixed_window_utterance_{stamp}_{utterances}.trim.wav"
            wav_stats = export_latest_pcm_to_wav(args.audio_pcm, wav_path, sample_rate=args.sample_rate)
            print(
                f"utterance_detected duration_ms={event['duration_ms']} "
                f"peak={_fmt_db(wav_stats.get('peak_dbfs'))} wav={wav_path}",
                flush=True,
            )
            result = await run_once(
                source="audio_file",
                audio_path=str(wav_path),
                vad_backend="energy",
                vad_threshold=args.vad_threshold,
                asr_backend=args.asr_backend,
                asr_model_path=args.asr_model_path,
                device=args.device,
                no_agent=args.no_agent,
                trim_speech=True,
                speech_trim_path=str(trim_path),
                speech_trim_threshold=args.speech_trim_threshold,
                speech_trim_padding_ms=args.speech_trim_padding_ms,
            )
            print(json.dumps(result, ensure_ascii=False, indent=2), flush=True)
            if args.once:
                return 0

        await asyncio.sleep(args.poll_ms / 1000)

    return 0 if utterances else 1


def _fmt_db(value: float | None) -> str:
    if value is None:
        return "None"
    return f"{value:.2f}dB"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Detect fixed-window utterances from latest_audio.pcm and run ASR.")
    parser.add_argument("--audio-pcm", default="runtime/latest_audio.pcm")
    parser.add_argument("--output-dir", default="runtime/manual_samples")
    parser.add_argument("--sample-rate", type=int, default=16000)
    parser.add_argument("--tail-ms", type=int, default=200)
    parser.add_argument("--poll-ms", type=int, default=100)
    parser.add_argument("--trigger-rms-dbfs", type=float, default=-42.0)
    parser.add_argument("--release-rms-dbfs", type=float, default=-48.0)
    parser.add_argument("--silence-ms", type=int, default=1000)
    parser.add_argument("--min-speech-ms", type=int, default=400)
    parser.add_argument("--cooldown-ms", type=int, default=1000)
    parser.add_argument("--speech-trim-threshold", type=float, default=0.003)
    parser.add_argument("--speech-trim-padding-ms", type=int, default=250)
    parser.add_argument("--vad-threshold", type=float, default=0.003)
    parser.add_argument("--asr-backend", choices=["fake", "sensevoice"], default="sensevoice")
    parser.add_argument("--asr-model-path", default="base_station/models/sensevoice-small")
    parser.add_argument("--device", default="cpu")
    parser.add_argument("--no-agent", action="store_true")
    parser.add_argument("--once", action="store_true", help="Exit after the first detected utterance.")
    parser.add_argument("--max-seconds", type=float, default=0.0, help="0 means run until interrupted.")
    parser.add_argument("--verbose", action="store_true")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    try:
        return asyncio.run(listen_and_transcribe(build_parser().parse_args(argv)))
    except KeyboardInterrupt:
        return 130
    except (OSError, ValueError, RuntimeError, ImportError) as exc:
        print(f"fixed_window_asr_demo failed: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
