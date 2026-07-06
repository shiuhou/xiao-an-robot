"""Resident voice runtime entry point for link-1 text transcripts.

The older asr_runtime module remains the single-shot test entry point. This
module owns the long-running loop that reuses one ApiRuntime instance.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
import time
from pathlib import Path
from typing import Any, TextIO

from base_station.api.runtime import ApiRuntime
from base_station.monitor.asr_runtime import build_asr_event, build_audio_file_event, build_output
from base_station.perception.mic_capture import choose_input_device, list_input_devices, record_wav, recording_sample_rate


SUPPORTED_SOURCES = {"text_loop", "local_mic"}
RESERVED_SOURCES = {"audio_file_loop"}


def build_voice_output(text: str, event: dict, result: dict) -> dict:
    """Build a compact debug object for each looped transcript."""

    output = build_output(text, event, result)
    openclaw_result = result.get("openclaw_result") if isinstance(result, dict) else None
    for key in (
        "display_text",
        "spoken_text",
        "suppress_auto_tts",
        "executed_actions",
        "skipped_actions",
    ):
        if key in output:
            continue
        if isinstance(result, dict) and key in result:
            output[key] = result[key]
            continue
        if isinstance(openclaw_result, dict) and key in openclaw_result:
            output[key] = openclaw_result[key]
    return output


def _write_latest_output(path: str | None, output: dict) -> None:
    if not path:
        return
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    payload = dict(output)
    payload["updated_at"] = time.strftime("%Y-%m-%dT%H:%M:%S%z")
    tmp = target.with_suffix(target.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(target)


def _recording_status(
    *,
    session_id: str,
    wav_path: Path,
    sample_rate: int,
    duration_seconds: float,
    previous_output: dict | None,
) -> dict:
    status = {
        "event_type": "voice.recording",
        "handled": False,
        "reason": "recording",
        "text": "",
        "session_id": session_id,
        "audio": {
            "audio_path": str(wav_path),
            "sample_rate": sample_rate,
            "duration_ms": int(duration_seconds * 1000),
            "channels": 1,
        },
    }
    if previous_output:
        status["previous_output"] = previous_output
    return status


async def process_text(
    runtime: Any,
    text: str,
    *,
    session_id: str = "voice-runtime",
    disable_companion_fast_path: bool = False,
) -> dict:
    """Send one terminal transcript through link 1 using an existing runtime."""

    transcript = text.strip()
    event = build_asr_event(transcript, source="text_loop")
    event["payload"]["session_id"] = session_id
    if disable_companion_fast_path:
        event["payload"]["disable_companion_fast_path"] = True
    result = await runtime.brain.handle_event(event)
    output = build_voice_output(transcript, event, result)
    _publish_latest_reply(
        runtime,
        output,
        event,
        session_id=session_id,
        source="voice_runtime.text_loop",
    )
    return output


async def process_audio_file(
    runtime: Any,
    audio_path: str,
    *,
    session_id: str = "voice-runtime",
    vad_backend: str = "energy",
    vad_threshold: float = 0.003,
    asr_backend: str = "sensevoice",
    asr_model_path: str | None = "base_station/models/sensevoice-small",
    device: str = "cpu",
    asr_language: str | None = None,
    asr_use_itn: bool = True,
    trim_speech: bool = True,
    speech_trim_path: str | None = None,
    speech_trim_threshold: float = 0.003,
    speech_trim_padding_ms: int = 250,
    speech_trim_min_speech_ms: int = 350,
    speech_trim_start_padding_ms: int | None = 250,
    speech_trim_end_padding_ms: int | None = 800,
    disable_companion_fast_path: bool = False,
) -> dict:
    """Run one microphone WAV through VAD/ASR and then link-1 OpenClaw routing."""

    event, prepared = build_audio_file_event(
        audio_path=audio_path,
        vad_backend=vad_backend,
        vad_threshold=vad_threshold,
        asr_backend=asr_backend,
        asr_model_path=asr_model_path,
        device=device,
        asr_language=asr_language,
        asr_use_itn=asr_use_itn,
        trim_speech=trim_speech,
        speech_trim_path=speech_trim_path,
        speech_trim_threshold=speech_trim_threshold,
        speech_trim_padding_ms=speech_trim_padding_ms,
        speech_trim_min_speech_ms=speech_trim_min_speech_ms,
        speech_trim_start_padding_ms=speech_trim_start_padding_ms,
        speech_trim_end_padding_ms=speech_trim_end_padding_ms,
    )
    if event is None:
        return prepared

    transcript = str(prepared["text"])
    event["payload"]["source"] = "local_mic"
    event["payload"]["session_id"] = session_id
    if disable_companion_fast_path:
        event["payload"]["disable_companion_fast_path"] = True
    result = await runtime.brain.handle_event(event)
    output = build_voice_output(transcript, event, result)
    _publish_latest_reply(
        runtime,
        output,
        event,
        session_id=session_id,
        source="voice_runtime.local_mic",
    )
    return output


async def run_text_loop(
    *,
    runtime_factory: Any = ApiRuntime,
    input_stream: TextIO | None = None,
    output_stream: TextIO | None = None,
    error_stream: TextIO | None = None,
    db_path: str = "agent/data/xiao_an.db",
    gateway_url: str = "ws://127.0.0.1:8765/agent",
    session_id: str = "voice-runtime",
    verbose: bool = False,
    prompt: bool = True,
    latest_output_path: str | None = None,
    disable_companion_fast_path: bool = False,
) -> int:
    """Run the resident text loop until EOF or Ctrl+C.

    Returns the number of non-empty transcript lines processed.
    """

    input_stream = input_stream or sys.stdin
    output_stream = output_stream or sys.stdout
    error_stream = error_stream or sys.stderr
    runtime = runtime_factory(
        db_path=db_path,
        robot_ws_url=gateway_url,
        verbose=verbose,
    )
    handled_count = 0
    try:
        while True:
            if prompt:
                print("voice> ", end="", file=output_stream, flush=True)
            try:
                line = input_stream.readline()
            except KeyboardInterrupt:
                print("\nvoice_runtime stopped.", file=error_stream, flush=True)
                return handled_count
            if line == "":
                return handled_count
            text = line.strip()
            if not text:
                continue
            output = await process_text(
                runtime,
                text,
                session_id=session_id,
                disable_companion_fast_path=disable_companion_fast_path,
            )
            handled_count += 1
            if verbose:
                print(json.dumps(output, ensure_ascii=False, indent=2), file=output_stream, flush=True)
            else:
                print(json.dumps(_compact_output(output), ensure_ascii=False), file=output_stream, flush=True)
            _write_latest_output(latest_output_path, output)
    finally:
        close = getattr(runtime, "close", None)
        if callable(close):
            close()


async def run_local_mic_loop(
    *,
    runtime_factory: Any = ApiRuntime,
    output_stream: TextIO | None = None,
    error_stream: TextIO | None = None,
    db_path: str = "agent/data/xiao_an.db",
    gateway_url: str = "ws://127.0.0.1:8765/agent",
    session_id: str = "voice-runtime",
    verbose: bool = False,
    device_name: str | None = None,
    output_dir: str = "runtime/voice_runtime_audio",
    duration_seconds: float = 5.0,
    sample_rate: int = 16000,
    asr_backend: str = "sensevoice",
    asr_model_path: str | None = "base_station/models/sensevoice-small",
    asr_device: str = "cpu",
    asr_language: str | None = None,
    asr_use_itn: bool = True,
    vad_backend: str = "energy",
    vad_threshold: float = 0.003,
    trim_speech: bool = True,
    speech_trim_threshold: float = 0.003,
    speech_trim_padding_ms: int = 250,
    speech_trim_min_speech_ms: int = 350,
    speech_trim_start_padding_ms: int | None = 250,
    speech_trim_end_padding_ms: int | None = 800,
    once: bool = False,
    latest_output_path: str | None = None,
    disable_companion_fast_path: bool = False,
) -> int:
    """Run fixed-window local microphone capture through ASR and link 1."""

    output_stream = output_stream or sys.stdout
    error_stream = error_stream or sys.stderr
    devices = list_input_devices()
    selected_device = choose_input_device(devices, device_name)
    active_sample_rate = recording_sample_rate(selected_device, sample_rate)
    audio_dir = Path(output_dir)
    audio_dir.mkdir(parents=True, exist_ok=True)
    runtime = runtime_factory(
        db_path=db_path,
        robot_ws_url=gateway_url,
        verbose=verbose,
    )
    handled_count = 0
    last_output: dict | None = None

    print(
        "voice_runtime local_mic "
        f"device={selected_device.get('index')}:{selected_device.get('name')} "
        f"window={duration_seconds:.1f}s",
        file=error_stream,
        flush=True,
    )
    _write_latest_output(
        latest_output_path,
        {
            "event_type": "voice.runtime_started",
            "handled": False,
            "reason": "starting",
            "text": "",
            "session_id": session_id,
            "device": {
                "index": selected_device.get("index"),
                "name": selected_device.get("name"),
                "backend": selected_device.get("backend"),
                "sample_rate": active_sample_rate,
            },
            "window_seconds": duration_seconds,
        },
    )

    try:
        while True:
            stamp = time.strftime("%Y%m%d_%H%M%S")
            wav_path = audio_dir / f"voice_runtime_{stamp}_{handled_count + 1}.wav"
            trim_path = audio_dir / f"voice_runtime_{stamp}_{handled_count + 1}.trim.wav"
            _write_latest_output(
                latest_output_path,
                _recording_status(
                    session_id=session_id,
                    wav_path=wav_path,
                    sample_rate=active_sample_rate,
                    duration_seconds=duration_seconds,
                    previous_output=last_output,
                ),
            )
            record_wav(
                device=selected_device,
                output_path=wav_path,
                duration_seconds=duration_seconds,
                sample_rate=active_sample_rate,
                channels=1,
            )
            output = await process_audio_file(
                runtime,
                str(wav_path),
                session_id=session_id,
                vad_backend=vad_backend,
                vad_threshold=vad_threshold,
                asr_backend=asr_backend,
                asr_model_path=asr_model_path,
                device=asr_device,
                asr_language=asr_language,
                asr_use_itn=asr_use_itn,
                trim_speech=trim_speech,
                speech_trim_path=str(trim_path) if trim_speech else None,
                speech_trim_threshold=speech_trim_threshold,
                speech_trim_padding_ms=speech_trim_padding_ms,
                speech_trim_min_speech_ms=speech_trim_min_speech_ms,
                speech_trim_start_padding_ms=speech_trim_start_padding_ms,
                speech_trim_end_padding_ms=speech_trim_end_padding_ms,
                disable_companion_fast_path=disable_companion_fast_path,
            )
            if output.get("event_type") == "asr.transcript":
                handled_count += 1
            if verbose:
                print(json.dumps(output, ensure_ascii=False, indent=2), file=output_stream, flush=True)
            else:
                print(json.dumps(_compact_output(output), ensure_ascii=False), file=output_stream, flush=True)
            _write_latest_output(latest_output_path, output)
            last_output = output
            if once:
                return handled_count
    except KeyboardInterrupt:
        print("\nvoice_runtime local_mic stopped.", file=error_stream, flush=True)
        return handled_count
    finally:
        close = getattr(runtime, "close", None)
        if callable(close):
            close()


def _publish_latest_reply(
    runtime: Any,
    output: dict,
    event: dict,
    *,
    session_id: str,
    source: str,
) -> None:
    set_latest = getattr(runtime, "_set_latest_reply", None)
    if not callable(set_latest):
        return

    display_text = _output_text(output, "display_text") or _output_text(output, "reply_text")
    spoken_text = _output_text(output, "spoken_text")
    reply_text = _output_text(output, "reply_text")
    metadata = {
        "route": output.get("route"),
        "reason": output.get("reason"),
        "event_type": event.get("type"),
        "transcript": output.get("text", ""),
        "payload_source": (event.get("payload") or {}).get("source")
        if isinstance(event.get("payload"), dict)
        else None,
    }
    latest = set_latest(
        notification_type=str(event.get("type") or "asr.transcript"),
        display_text=display_text,
        spoken_text=spoken_text,
        reply_text=reply_text,
        tool_calls=[],
        metadata=metadata,
        session_id=session_id,
        source=source,
        suppress_auto_tts=bool(output.get("suppress_auto_tts", False)),
        execution_result=output,
    )
    output["latest_reply"] = _latest_reply_summary(latest)


def _latest_reply_summary(latest: Any) -> dict:
    if not isinstance(latest, dict):
        return {}
    summary = {}
    for key in (
        "type",
        "notification_type",
        "display_text",
        "spoken_text",
        "reply_text",
        "output_text",
        "session_id",
        "source",
    ):
        if key in latest:
            summary[key] = latest[key]
    return summary


def _output_text(output: dict, key: str) -> str:
    value = output.get(key, "")
    return value.strip() if isinstance(value, str) else ""


def _compact_output(output: dict) -> dict:
    compact = {}
    for key in (
        "text",
        "event_type",
        "handled",
        "route",
        "reason",
        "display_text",
        "spoken_text",
        "reply_text",
        "executed_actions",
        "skipped_actions",
        "openclaw_error",
        "latest_reply",
    ):
        if key in output:
            compact[key] = output[key]
    return compact


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run Xiao An's resident voice runtime.")
    parser.add_argument(
        "--source",
        choices=sorted(SUPPORTED_SOURCES | RESERVED_SOURCES),
        default="text_loop",
        help="Resident input source.",
    )
    parser.add_argument("--db-path", default="agent/data/xiao_an.db")
    parser.add_argument("--gateway-url", default="ws://127.0.0.1:8765/agent")
    parser.add_argument("--session-id", default="voice-runtime")
    parser.add_argument("--verbose", action="store_true", help="Print full JSON output for each transcript.")
    parser.add_argument("--no-prompt", action="store_true", help="Disable the interactive prompt.")
    parser.add_argument("--list-devices", action="store_true", help="List local microphone input devices and exit.")
    parser.add_argument("--device", default=None, help="Local microphone device index, id, or name substring.")
    parser.add_argument("--duration", type=float, default=5.0, help="Fixed local_mic capture window in seconds.")
    parser.add_argument("--sample-rate", type=int, default=16000)
    parser.add_argument("--audio-output-dir", default="runtime/voice_runtime_audio")
    parser.add_argument("--once", action="store_true", help="Exit after one local_mic capture window.")
    parser.add_argument("--asr-backend", choices=["fake", "sensevoice"], default="sensevoice")
    parser.add_argument("--asr-model-path", default="base_station/models/sensevoice-small")
    parser.add_argument("--asr-device", default="cpu")
    parser.add_argument("--asr-language", default=None, help="Optional SenseVoice language hint, e.g. zh or auto.")
    parser.add_argument("--no-asr-itn", dest="asr_use_itn", action="store_false", help="Disable SenseVoice ITN.")
    parser.add_argument("--vad-backend", choices=["fake", "energy", "silero"], default="energy")
    parser.add_argument("--vad-threshold", type=float, default=0.003)
    parser.add_argument("--trim-speech", action="store_true", default=True)
    parser.add_argument("--no-trim-speech", dest="trim_speech", action="store_false")
    parser.add_argument("--speech-trim-threshold", type=float, default=0.003)
    parser.add_argument("--speech-trim-padding-ms", type=int, default=250)
    parser.add_argument("--speech-trim-min-speech-ms", type=int, default=350)
    parser.add_argument("--speech-trim-start-padding-ms", type=int, default=250)
    parser.add_argument("--speech-trim-end-padding-ms", type=int, default=800)
    parser.add_argument("--latest-output", default=None, help="Write the latest loop output JSON to this path.")
    parser.add_argument(
        "--disable-companion-fast-path",
        action="store_true",
        help="Route ASR transcripts to OpenClaw without local companion care pre-response.",
    )
    return parser.parse_args(argv)


async def main(args: argparse.Namespace | None = None) -> int:
    if args is None:
        args = parse_args()
    if args.source not in SUPPORTED_SOURCES:
        raise NotImplementedError(f"--source {args.source} is reserved but not implemented yet.")
    if args.list_devices:
        for device in list_input_devices():
            print(
                f"{device['index']}: {device['name']} "
                f"(backend={device.get('backend')}, inputs={device['max_input_channels']}, "
                f"default_rate={device['default_sample_rate']:.0f})"
            )
        return 0
    if args.source == "local_mic":
        await run_local_mic_loop(
            db_path=args.db_path,
            gateway_url=args.gateway_url,
            session_id=args.session_id,
            verbose=args.verbose,
            device_name=args.device,
            output_dir=args.audio_output_dir,
            duration_seconds=args.duration,
            sample_rate=args.sample_rate,
            asr_backend=args.asr_backend,
            asr_model_path=args.asr_model_path,
            asr_device=args.asr_device,
            asr_language=args.asr_language,
            asr_use_itn=args.asr_use_itn,
            vad_backend=args.vad_backend,
            vad_threshold=args.vad_threshold,
            trim_speech=args.trim_speech,
            speech_trim_threshold=args.speech_trim_threshold,
            speech_trim_padding_ms=args.speech_trim_padding_ms,
            speech_trim_min_speech_ms=args.speech_trim_min_speech_ms,
            speech_trim_start_padding_ms=args.speech_trim_start_padding_ms,
            speech_trim_end_padding_ms=args.speech_trim_end_padding_ms,
            once=args.once,
            latest_output_path=args.latest_output,
            disable_companion_fast_path=args.disable_companion_fast_path,
        )
        return 0
    await run_text_loop(
        db_path=args.db_path,
        gateway_url=args.gateway_url,
        session_id=args.session_id,
        verbose=args.verbose,
        prompt=not args.no_prompt,
        latest_output_path=args.latest_output,
        disable_companion_fast_path=args.disable_companion_fast_path,
    )
    return 0


def run_cli(argv: list[str] | None = None) -> int:
    try:
        return asyncio.run(main(parse_args(argv)))
    except KeyboardInterrupt:
        print("\nvoice_runtime stopped.", file=sys.stderr)
        return 0
    except (ValueError, RuntimeError, ImportError, NotImplementedError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(run_cli())
