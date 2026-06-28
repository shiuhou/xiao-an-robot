"""Standalone ASR transcript runtime for local companion request testing."""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from typing import Any

from agent.core.brain import XiaoAnBrain
from base_station.perception.asr import FakeASRBackend, PATTERN_TRANSCRIPTS, SenseVoiceASRBackend
from base_station.perception.audio_source import load_wav_audio_file
from base_station.perception.vad import EnergyVADBackend, FakeVADBackend, SileroVADBackend


ASR_TRANSCRIPT_EVENT = "asr.transcript"
ASR_NO_SPEECH_EVENT = "asr.no_speech"
PATTERN_TEXT = PATTERN_TRANSCRIPTS


def resolve_transcript(text: str | None = None, pattern: str | None = None) -> str:
    """Resolve transcript text, with explicit text taking priority over pattern."""

    if text is not None:
        return text

    selected_pattern = pattern or "normal"
    try:
        return PATTERN_TEXT[selected_pattern]
    except KeyError as exc:
        supported = ", ".join(sorted(PATTERN_TEXT))
        raise ValueError(f"Unsupported ASR pattern: {selected_pattern}. Supported patterns: {supported}.") from exc


def audio_metadata(audio_clip: dict | None) -> dict | None:
    if not audio_clip:
        return None
    return {
        "source": audio_clip.get("source"),
        "audio_path": audio_clip.get("audio_path"),
        "sample_rate": audio_clip.get("sample_rate"),
        "duration_ms": audio_clip.get("duration_ms"),
        "channels": audio_clip.get("channels"),
    }


def build_asr_event(
    text: str,
    *,
    source: str | None = None,
    vad: dict | None = None,
    asr: dict | None = None,
    audio: dict | None = None,
) -> dict:
    payload = {
        "text": text,
    }
    if source is not None:
        payload["source"] = source
    if vad is not None:
        payload["vad"] = vad
    if asr is not None:
        payload["asr"] = asr
    if audio is not None:
        payload["audio"] = audio
    return {
        "type": ASR_TRANSCRIPT_EVENT,
        "payload": payload,
    }


def build_output(text: str, event: dict, result: dict) -> dict:
    output = {
        "text": text,
        "event_type": event.get("type"),
        "event": event,
        "handled": result.get("handled", False),
        "reason": result.get("reason"),
        "trigger_result": result.get("trigger_result"),
    }
    for key in (
        "route",
        "reply_text",
        "executed_actions",
        "skipped_actions",
        "companion_result",
        "openclaw_result",
        "openclaw_error",
        "openclaw_event_type",
    ):
        if key in result:
            output[key] = result[key]
    return output


def build_no_speech_output(vad: dict, audio: dict | None = None) -> dict:
    return {
        "event_type": ASR_NO_SPEECH_EVENT,
        "handled": False,
        "reason": "vad_no_speech",
        "vad": vad,
        "audio": audio,
    }


def create_vad_backend(
    backend: str,
    *,
    pattern: str = "speech",
    model_path: str | None = None,
    threshold: float = 0.01,
):
    if backend == "fake":
        return FakeVADBackend(pattern=pattern)
    if backend == "energy":
        return EnergyVADBackend(threshold=threshold)
    if backend == "silero":
        return SileroVADBackend(model_path=model_path, threshold=threshold)
    raise ValueError(f"Unsupported VAD backend: {backend}")


def create_asr_backend(
    backend: str,
    *,
    fake_transcript: str | None = None,
    pattern: str | None = None,
    model_path: str | None = None,
    device: str = "cpu",
):
    if backend == "fake":
        return FakeASRBackend(transcript=fake_transcript, pattern=pattern)
    if backend == "sensevoice":
        return SenseVoiceASRBackend(model_dir=model_path, device=device)
    raise ValueError(f"Unsupported ASR backend: {backend}")


def build_audio_file_event(
    *,
    audio_path: str,
    vad_backend: str = "fake",
    vad_pattern: str = "speech",
    vad_model_path: str | None = None,
    vad_threshold: float = 0.01,
    asr_backend: str = "fake",
    fake_transcript: str | None = None,
    pattern: str | None = None,
    asr_model_path: str | None = None,
    device: str = "cpu",
) -> tuple[dict | None, dict]:
    audio_clip = load_wav_audio_file(audio_path)
    audio = audio_metadata(audio_clip)
    vad = create_vad_backend(
        vad_backend,
        pattern=vad_pattern,
        model_path=vad_model_path,
        threshold=vad_threshold,
    ).analyze(audio_clip)
    if not vad.get("speech_detected", False):
        return None, build_no_speech_output(vad=vad, audio=audio)

    asr = create_asr_backend(
        asr_backend,
        fake_transcript=fake_transcript,
        pattern=pattern,
        model_path=asr_model_path,
        device=device,
    ).transcribe(audio_clip)
    text = str(asr.get("text") or "").strip()
    if not text:
        return None, {
            "event_type": "asr.empty_transcript",
            "handled": False,
            "reason": "asr_empty_transcript",
            "vad": vad,
            "asr": asr,
            "audio": audio,
        }

    event = build_asr_event(
        text,
        source="audio_file",
        vad=vad,
        asr=asr,
        audio=audio,
    )
    return event, {"text": text, "vad": vad, "asr": asr, "audio": audio}


async def run_once(
    text: str | None = None,
    pattern: str | None = None,
    source: str | None = None,
    audio_path: str | None = None,
    vad_backend: str = "fake",
    vad_pattern: str = "speech",
    vad_model_path: str | None = None,
    vad_threshold: float = 0.01,
    asr_backend: str = "fake",
    fake_transcript: str | None = None,
    asr_model_path: str | None = None,
    device: str = "cpu",
    no_agent: bool = False,
    gateway_url: str = "ws://127.0.0.1:8765/agent",
    brain: Any | None = None,
) -> dict:
    selected_source = source
    if selected_source is None:
        selected_source = "audio_file" if audio_path else ("text" if text is not None else "pattern")

    if selected_source == "audio_file":
        if not audio_path:
            raise ValueError("--audio-path is required when --source audio_file")
        event, prepared = build_audio_file_event(
            audio_path=audio_path,
            vad_backend=vad_backend,
            vad_pattern=vad_pattern,
            vad_model_path=vad_model_path,
            vad_threshold=vad_threshold,
            asr_backend=asr_backend,
            fake_transcript=fake_transcript,
            pattern=pattern,
            asr_model_path=asr_model_path,
            device=device,
        )
        if event is None:
            return prepared
        transcript = str(prepared["text"])
    elif selected_source == "text":
        if text is None:
            raise ValueError("--text is required when --source text")
        transcript = resolve_transcript(text=text, pattern=pattern)
        event = build_asr_event(transcript, source="text")
    elif selected_source == "pattern":
        transcript = resolve_transcript(text=text, pattern=pattern)
        event = build_asr_event(transcript, source="pattern")
    else:
        raise ValueError(f"Unsupported ASR source: {selected_source}")

    if no_agent:
        return build_output(transcript, event, {"handled": False, "reason": "no_agent"})

    active_brain = brain or XiaoAnBrain(gateway_url=gateway_url)

    try:
        result = await active_brain.handle_event(event)
    finally:
        if brain is None:
            active_brain.close()

    return build_output(transcript, event, result)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run a local ASR transcript event through XiaoAnBrain.")
    parser.add_argument("--source", choices=["text", "pattern", "audio_file"], default=None, help="ASR input source.")
    parser.add_argument("--text", default=None, help="Direct ASR transcript text.")
    parser.add_argument(
        "--pattern",
        choices=sorted(PATTERN_TEXT),
        default=None,
        help="Preset transcript pattern.",
    )
    parser.add_argument("--audio-path", default=None, help="Local WAV file for --source audio_file.")
    parser.add_argument("--vad-backend", choices=["fake", "energy", "silero"], default="fake")
    parser.add_argument("--vad-pattern", choices=["speech", "silence"], default="speech")
    parser.add_argument("--vad-model-path", default=None, help="Local Silero VAD model path.")
    parser.add_argument("--vad-threshold", type=float, default=0.01, help="Energy/Silero VAD threshold.")
    parser.add_argument("--asr-backend", choices=["fake", "sensevoice"], default="fake")
    parser.add_argument("--fake-transcript", default=None, help="Transcript returned by fake ASR for audio_file.")
    parser.add_argument("--asr-model-path", default=None, help="Local SenseVoice model directory.")
    parser.add_argument("--device", default="cpu", help="ASR/VAD device for future real backends.")
    parser.add_argument("--no-agent", action="store_true", help="Build ASR output without initializing XiaoAnBrain.")
    parser.add_argument("--gateway-url", default="ws://127.0.0.1:8765/agent", help="Base station /agent URL.")
    parser.add_argument("--verbose", action="store_true", help="Print JSON result.")
    return parser.parse_args(argv)


async def main(args: argparse.Namespace | None = None) -> dict:
    if args is None:
        args = parse_args()
    output = await run_once(
        text=args.text,
        pattern=args.pattern,
        source=args.source,
        audio_path=args.audio_path,
        vad_backend=args.vad_backend,
        vad_pattern=args.vad_pattern,
        vad_model_path=args.vad_model_path,
        vad_threshold=args.vad_threshold,
        asr_backend=args.asr_backend,
        fake_transcript=args.fake_transcript,
        asr_model_path=args.asr_model_path,
        device=args.device,
        no_agent=args.no_agent,
        gateway_url=args.gateway_url,
    )
    if args.verbose:
        print(json.dumps(output, ensure_ascii=False, indent=2))
    return output


def run_cli(argv: list[str] | None = None) -> int:
    try:
        asyncio.run(main(parse_args(argv)))
    except KeyboardInterrupt:
        raise
    except (ValueError, FileNotFoundError, RuntimeError, ImportError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(run_cli())
