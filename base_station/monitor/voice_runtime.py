"""Resident voice runtime entry point for link-1 text transcripts.

The older asr_runtime module remains the single-shot test entry point. This
module owns the long-running loop that reuses one ApiRuntime instance.
"""

from __future__ import annotations

import argparse
import asyncio
import audioop
import json
import os
import struct
import sys
import threading
import time
import wave
from pathlib import Path
from typing import Any, TextIO

from agent.core.work_mode import WorkModeStore
from base_station.api.runtime import ApiRuntime
from base_station.integration_console.fast_demo_brain import (
    build_fast_demo_voice_output,
    build_reminder_record,
    execute_robot_plan,
    parse_reminder_due_at,
    publish_fast_demo_dashboard_capture,
)
from base_station.monitor.asr_runtime import build_asr_event, build_audio_file_event, build_output, create_asr_backend
from base_station.perception.asr import SenseVoiceASRBackend
from base_station.perception.mic_capture import (
    PersistentWavRecorder,
    choose_input_device,
    list_input_devices,
    recording_sample_rate,
)


SUPPORTED_SOURCES = {"text_loop", "local_mic"}
RESERVED_SOURCES = {"audio_file_loop"}
DECISION_MODES = {"asr_only", "openclaw", "local_demo"}
CAPTURE_MODES = {"fixed_window", "until_mic_off"}
DEFAULT_POST_TTS_DISCARD_SECONDS = 2.0
DEFAULT_CONTINUOUS_POLL_SECONDS = 0.25
DEFAULT_CONTINUOUS_MAX_SECONDS = 180.0


def build_voice_output(text: str, event: dict, result: dict) -> dict:
    """Build a compact debug object for each looped transcript."""

    output = build_output(text, event, result)
    openclaw_result = result.get("openclaw_result") if isinstance(result, dict) else None
    for key in (
        "display_text",
        "spoken_text",
        "tts_text",
        "tts_source",
        "tts_tool",
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
    if not _output_text(output, "tts_text"):
        tts_text = _output_tts_text(output)
        if tts_text:
            output["tts_text"] = tts_text
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
        status["previous_output"] = _previous_voice_output(previous_output)
    return status


def _recording_until_mic_off_status(
    *,
    session_id: str,
    wav_path: Path,
    sample_rate: int,
    previous_output: dict | None,
) -> dict:
    status = {
        "event_type": "voice.recording",
        "handled": False,
        "reason": "recording_until_mic_off",
        "text": "",
        "session_id": session_id,
        "audio": {
            "audio_path": str(wav_path),
            "sample_rate": sample_rate,
            "channels": 1,
            "duration_ms": None,
            "stop_condition": "mic_recognition_disabled",
        },
    }
    if previous_output:
        status["previous_output"] = _previous_voice_output(previous_output)
    return status


def _muted_status(session_id: str, previous_output: dict | None) -> dict:
    status = {
        "event_type": "voice.muted",
        "handled": False,
        "reason": "mic_recognition_disabled",
        "text": "",
        "session_id": session_id,
    }
    previous = _meaningful_voice_output(previous_output or {})
    if previous:
        status["previous_output"] = previous
    return status


def _post_tts_discard_status(
    session_id: str,
    previous_output: dict | None,
    duration_seconds: float,
) -> dict:
    status = {
        "event_type": "voice.post_tts_discard",
        "handled": False,
        "reason": "post_tts_discard",
        "text": "",
        "session_id": session_id,
        "duration_ms": int(duration_seconds * 1000),
        "tts_text": _output_tts_text(previous_output or {}),
    }
    previous = _meaningful_voice_output(previous_output or {})
    if previous:
        status["previous_output"] = previous
    return status


def _mic_recognition_allowed() -> bool:
    snapshot = WorkModeStore.from_env().snapshot()
    if not snapshot.get("persisted"):
        return True
    return bool(snapshot.get("system_enabled") and snapshot.get("mic_recognition_enabled"))


def _post_tts_discard_seconds() -> float:
    raw = os.environ.get("XIAOAN_VOICE_POST_TTS_DISCARD_SECONDS")
    if raw is None:
        return DEFAULT_POST_TTS_DISCARD_SECONDS
    try:
        value = float(raw)
    except ValueError:
        return DEFAULT_POST_TTS_DISCARD_SECONDS
    return max(0.0, min(value, 10.0))


def _continuous_max_seconds() -> float:
    raw = os.environ.get("XIAOAN_VOICE_CONTINUOUS_MAX_SECONDS")
    if raw is None:
        return DEFAULT_CONTINUOUS_MAX_SECONDS
    try:
        value = float(raw)
    except ValueError:
        return DEFAULT_CONTINUOUS_MAX_SECONDS
    return max(1.0, min(value, 900.0))


def _openclaw_pending_output(text: str, event: dict) -> dict:
    return build_voice_output(
        text,
        event,
        {
            "handled": False,
            "route": "voice_runtime.openclaw_pending",
            "reason": "openclaw_pending",
            "trigger_result": None,
            "display_text": "",
            "spoken_text": "",
            "reply_text": "",
        },
    )


def _has_meaningful_transcript_text(text: str) -> bool:
    return any(char.isalnum() for char in text)


def _release_active_voice_episode(status: str, result: dict[str, Any]) -> None:
    store = WorkModeStore.from_env()
    snapshot = store.snapshot()
    if snapshot.get("episode_state") != "running":
        return
    if snapshot.get("active_chain") not in {"link1", "link3"}:
        return
    store.release_episode(str(snapshot.get("active_run_id") or ""), status=status, result=result)


async def process_text(
    runtime: Any,
    text: str,
    *,
    session_id: str = "voice-runtime",
    disable_companion_fast_path: bool = False,
    gateway_url: str = "ws://127.0.0.1:8765/agent",
    local_demo_reminders_path: str | None = None,
) -> dict:
    """Send one terminal transcript through link 1 using an existing runtime."""

    transcript = text.strip()
    event = build_asr_event(transcript, source="text_loop")
    event["payload"]["session_id"] = session_id
    if disable_companion_fast_path:
        event["payload"]["disable_companion_fast_path"] = True
    result = await runtime.brain.handle_event(event)
    output = build_voice_output(transcript, event, result)
    _maybe_schedule_openclaw_reminder_fallback(
        output,
        transcript,
        reminders_path=local_demo_reminders_path,
        send_to_robot=True,
        allow_motion=False,
        gateway_url=gateway_url,
    )
    _publish_latest_reply(
        runtime,
        output,
        event,
        session_id=session_id,
        source="voice_runtime.text_loop",
    )
    return output


async def process_audio_file(
    runtime: Any | None,
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
    latest_output_path: str | None = None,
    decision_mode: str = "openclaw",
    local_demo_link: str = "fast1",
    local_demo_send_to_robot: bool = False,
    local_demo_allow_motion: bool = False,
    gateway_url: str = "ws://127.0.0.1:8765/agent",
    local_demo_reminders_path: str | None = None,
    asr_backend_instance: Any | None = None,
    completed_mic_segment: bool = False,
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
        asr_backend_instance=asr_backend_instance,
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

    transcript = str(prepared["text"]).strip()
    if not _has_meaningful_transcript_text(transcript):
        payload = event.get("payload") if isinstance(event.get("payload"), dict) else {}
        output = {
            "event_type": "asr.empty_transcript",
            "handled": False,
            "reason": "asr_nonlexical_transcript",
            "text": transcript,
            "vad": payload.get("vad"),
            "asr": payload.get("asr"),
            "audio": payload.get("audio"),
        }
        _release_active_voice_episode("ignored", output)
        return output
    event["payload"]["source"] = "local_mic"
    event["payload"]["session_id"] = session_id
    if completed_mic_segment:
        event["payload"]["completed_mic_segment"] = True
    if disable_companion_fast_path:
        event["payload"]["disable_companion_fast_path"] = True
    if decision_mode == "asr_only":
        return build_voice_output(
            transcript,
            event,
            {
                "handled": True,
                "route": "voice_runtime.asr_only",
                "reason": "asr_only",
                "reply_text": "",
                "display_text": "",
                "spoken_text": "",
            },
        )
    if decision_mode == "local_demo":
        output = build_fast_demo_voice_output(transcript, event, link=local_demo_link)
        _write_latest_output(latest_output_path, output)
        execution = await execute_robot_plan(
            output.get("fast_demo_decision") if isinstance(output.get("fast_demo_decision"), dict) else {},
            gateway_url=gateway_url,
            send_to_robot=local_demo_send_to_robot,
            allow_motion=local_demo_allow_motion,
        )
        output["robot_execution"] = execution
        output["executed_actions"] = execution.get("executed_actions", [])
        output["skipped_actions"] = execution.get("skipped_actions", [])
        dashboard_capture = publish_fast_demo_dashboard_capture(
            output.get("fast_demo_decision") if isinstance(output.get("fast_demo_decision"), dict) else {},
            transcript,
        )
        if dashboard_capture is not None:
            output["dashboard_capture"] = dashboard_capture
        reminder_record = build_reminder_record(
            output.get("fast_demo_decision") if isinstance(output.get("fast_demo_decision"), dict) else {},
            transcript=transcript,
            send_to_robot=local_demo_send_to_robot,
            allow_motion=local_demo_allow_motion,
            gateway_url=gateway_url,
        )
        if reminder_record is not None:
            _append_fast_demo_reminder(local_demo_reminders_path, reminder_record)
            output["scheduled_reminder"] = reminder_record
        return output
    if runtime is None:
        raise RuntimeError("openclaw decision mode requires a runtime")
    _write_latest_output(latest_output_path, _openclaw_pending_output(transcript, event))
    result = await runtime.brain.handle_event(event)
    output = build_voice_output(transcript, event, result)
    _maybe_schedule_openclaw_reminder_fallback(
        output,
        transcript,
        reminders_path=local_demo_reminders_path,
        send_to_robot=True,
        allow_motion=False,
        gateway_url=gateway_url,
    )
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
    decision_mode: str = "openclaw",
    local_demo_link: str = "fast1",
    local_demo_send_to_robot: bool = False,
    local_demo_allow_motion: bool = False,
    local_demo_reminders_path: str | None = None,
) -> int:
    """Run the resident text loop until EOF or Ctrl+C.

    Returns the number of non-empty transcript lines processed.
    """

    input_stream = input_stream or sys.stdin
    output_stream = output_stream or sys.stdout
    error_stream = error_stream or sys.stderr
    if decision_mode not in DECISION_MODES:
        raise ValueError(f"unsupported_decision_mode:{decision_mode}")
    runtime = None
    if decision_mode == "openclaw":
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
                gateway_url=gateway_url,
                local_demo_reminders_path=local_demo_reminders_path,
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
    decision_mode: str = "openclaw",
    local_demo_link: str = "fast1",
    local_demo_send_to_robot: bool = False,
    local_demo_allow_motion: bool = False,
    local_demo_reminders_path: str | None = None,
    capture_mode: str = "fixed_window",
    work_mode_gated: bool = False,
) -> int:
    """Run fixed-window local microphone capture through ASR and link 1."""

    output_stream = output_stream or sys.stdout
    error_stream = error_stream or sys.stderr
    devices = list_input_devices()
    selected_device = choose_input_device(devices, device_name)
    active_sample_rate = recording_sample_rate(selected_device, sample_rate)
    audio_dir = Path(output_dir)
    audio_dir.mkdir(parents=True, exist_ok=True)
    if decision_mode not in DECISION_MODES:
        raise ValueError(f"unsupported_decision_mode:{decision_mode}")
    if capture_mode not in CAPTURE_MODES:
        raise ValueError(f"unsupported_capture_mode:{capture_mode}")
    runtime = None
    if decision_mode == "openclaw":
        runtime = runtime_factory(
            db_path=db_path,
            robot_ws_url=gateway_url,
            verbose=verbose,
        )
    asr_backend_instance = create_asr_backend(
        asr_backend,
        model_path=asr_model_path,
        device=asr_device,
        language=asr_language,
        use_itn=asr_use_itn,
    )
    preload_thread, preload_state = _start_asr_backend_preload(asr_backend_instance)
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
        recorder = PersistentWavRecorder(
            device=selected_device,
            sample_rate=active_sample_rate,
            channels=1,
        )
        recorder_context = recorder.__enter__()
        del recorder_context
    except Exception:
        close = getattr(runtime, "close", None) if runtime is not None else None
        if callable(close):
            close()
        raise

    try:
        while True:
            if work_mode_gated and not _mic_recognition_allowed():
                muted = _muted_status(session_id, last_output)
                _write_latest_output(latest_output_path, muted)
                recorder.discard_window(max(0.25, min(duration_seconds, 2.0)))
                last_output = muted
                if once:
                    return handled_count
                continue
            if _output_has_robot_tts(last_output):
                discard_seconds = min(duration_seconds, _post_tts_discard_seconds())
                if discard_seconds > 0:
                    post_tts = _post_tts_discard_status(session_id, last_output, discard_seconds)
                    _write_latest_output(latest_output_path, post_tts)
                    recorder.discard_window(discard_seconds)
                    last_output = post_tts
                    if once:
                        return handled_count
                    continue
            stamp = time.strftime("%Y%m%d_%H%M%S")
            wav_path = audio_dir / f"voice_runtime_{stamp}_{handled_count + 1}.wav"
            asr_wav_path = audio_dir / f"voice_runtime_{stamp}_{handled_count + 1}.asr.wav"
            trim_path = audio_dir / f"voice_runtime_{stamp}_{handled_count + 1}.trim.wav"
            completed_mic_segment = False
            _write_latest_output(
                latest_output_path,
                (
                    _recording_until_mic_off_status(
                        session_id=session_id,
                        wav_path=wav_path,
                        sample_rate=active_sample_rate,
                        previous_output=last_output,
                    )
                    if capture_mode == "until_mic_off"
                    else _recording_status(
                        session_id=session_id,
                        wav_path=wav_path,
                        sample_rate=active_sample_rate,
                        duration_seconds=duration_seconds,
                        previous_output=last_output,
                    )
                ),
            )
            if capture_mode == "until_mic_off":
                recorded_seconds = _record_until_mic_off(
                    recorder,
                    wav_path,
                    sample_rate=active_sample_rate,
                    channels=1,
                    poll_seconds=DEFAULT_CONTINUOUS_POLL_SECONDS,
                    max_seconds=_continuous_max_seconds(),
                )
                completed_mic_segment = True
                if recorded_seconds <= 0:
                    last_output = _muted_status(session_id, last_output)
                    _write_latest_output(latest_output_path, last_output)
                    if once:
                        return handled_count
                    continue
            else:
                recorder.record_window(wav_path, duration_seconds)
            _finish_asr_backend_preload(preload_thread, preload_state)
            preload_thread = None
            prepared_wav_path = _ensure_asr_wav_format(
                wav_path,
                asr_wav_path,
                sample_rate=sample_rate,
                channels=1,
            )
            output = await process_audio_file(
                runtime,
                str(prepared_wav_path),
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
                latest_output_path=latest_output_path,
                decision_mode=decision_mode,
                local_demo_link=local_demo_link,
                local_demo_send_to_robot=local_demo_send_to_robot,
                local_demo_allow_motion=local_demo_allow_motion,
                gateway_url=gateway_url,
                local_demo_reminders_path=local_demo_reminders_path,
                asr_backend_instance=asr_backend_instance,
                completed_mic_segment=completed_mic_segment,
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
        try:
            recorder.close()
        except Exception:
            pass
        close = getattr(runtime, "close", None) if runtime is not None else None
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


def _previous_voice_output(output: dict) -> dict:
    if not isinstance(output, dict):
        return {}
    if output.get("event_type") in {"voice.muted", "voice.recording", "voice.runtime_started"}:
        return _meaningful_voice_output(output)
    return output


def _meaningful_voice_output(output: dict) -> dict:
    current = output if isinstance(output, dict) else {}
    seen = set()
    while isinstance(current, dict) and current.get("event_type") in {
        "voice.muted",
        "voice.recording",
        "voice.runtime_started",
    }:
        marker = id(current)
        if marker in seen:
            return {}
        seen.add(marker)
        previous = current.get("previous_output")
        if not isinstance(previous, dict):
            return {}
        current = previous
    return current if isinstance(current, dict) else {}


def _output_tts_text(output: dict) -> str:
    if not isinstance(output, dict):
        return ""
    text = _output_text(output, "tts_text")
    if text:
        return text
    for action in output.get("executed_actions", []):
        text = _tts_text_from_executed_action(action)
        if text:
            return text
    nested = output.get("openclaw_result")
    if isinstance(nested, dict):
        return _output_tts_text(nested)
    return ""


def _output_has_robot_tts(output: dict | None) -> bool:
    if isinstance(output, dict) and output.get("event_type") == "voice.post_tts_discard":
        return False
    return bool(_output_tts_text(output or {}))


def _tts_text_from_executed_action(action: Any) -> str:
    if not isinstance(action, dict):
        return ""
    arguments = action.get("arguments")
    if not isinstance(arguments, dict):
        return ""
    name = str(action.get("name") or "")
    if name in {"robot.say", "xiaoan.robot.say"}:
        return str(arguments.get("text") or "").strip()
    if name in {"robot.care", "robot.care_for_user", "xiaoan.robot.care"}:
        return str(arguments.get("text") or arguments.get("reply_text") or "").strip()
    return ""


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
        "tts_text",
        "tts_source",
        "tts_tool",
        "reply_text",
        "executed_actions",
        "skipped_actions",
        "openclaw_error",
        "latest_reply",
    ):
        if key in output:
            compact[key] = output[key]
    return compact


def _write_silence_wav(path: Path, *, sample_rate: int = 16000, duration_seconds: float = 0.25) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    frame_count = max(1, int(sample_rate * duration_seconds))
    samples = struct.pack("<" + "h" * frame_count, *([0] * frame_count))
    with wave.open(str(path), "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(sample_rate)
        wav.writeframes(samples)


def _write_pcm_wav(path: Path, pcm: bytes, *, sample_rate: int, channels: int) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(path), "wb") as wav:
        wav.setnchannels(channels)
        wav.setsampwidth(2)
        wav.setframerate(sample_rate)
        wav.writeframes(pcm)


def _record_until_mic_off(
    recorder: Any,
    wav_path: Path,
    *,
    sample_rate: int,
    channels: int,
    poll_seconds: float,
    max_seconds: float,
) -> float:
    started = time.monotonic()
    chunks: list[bytes] = []
    while _mic_recognition_allowed():
        elapsed = time.monotonic() - started
        remaining = max_seconds - elapsed
        if remaining <= 0:
            break
        chunk_seconds = max(0.05, min(float(poll_seconds), remaining))
        chunks.append(recorder.read_window(chunk_seconds))
    pcm = b"".join(chunks)
    _write_pcm_wav(wav_path, pcm, sample_rate=sample_rate, channels=channels)
    return len(pcm) / max(1, sample_rate * channels * 2)


def _ensure_asr_wav_format(source: Path, target: Path, *, sample_rate: int = 16000, channels: int = 1) -> Path:
    with wave.open(str(source), "rb") as wav:
        source_channels = wav.getnchannels()
        source_width = wav.getsampwidth()
        source_rate = wav.getframerate()
        pcm = wav.readframes(wav.getnframes())

    if source_channels == channels and source_width == 2 and source_rate == sample_rate:
        return source

    if source_width != 2:
        pcm = audioop.lin2lin(pcm, source_width, 2)
        source_width = 2
    if source_channels != channels:
        if channels != 1:
            raise RuntimeError("voice_runtime ASR conversion only supports mono output.")
        if source_channels == 1:
            pass
        elif source_channels == 2:
            pcm = audioop.tomono(pcm, source_width, 0.5, 0.5)
        else:
            raise RuntimeError(f"voice_runtime cannot convert {source_channels} channels to mono.")
    if source_rate != sample_rate:
        pcm, _ = audioop.ratecv(pcm, source_width, channels, source_rate, sample_rate, None)

    target.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(target), "wb") as wav:
        wav.setnchannels(channels)
        wav.setsampwidth(2)
        wav.setframerate(sample_rate)
        wav.writeframes(pcm)
    return target


def _start_asr_backend_preload(backend: Any) -> tuple[threading.Thread | None, dict[str, Any]]:
    if not hasattr(backend, "_load_model") or not hasattr(backend, "_validate_model_dir"):
        return None, {"error": None}
    state: dict[str, Any] = {"error": None}

    def worker() -> None:
        try:
            model_dir = backend._validate_model_dir()
            backend._load_model(model_dir)
        except Exception as exc:  # pragma: no cover - surfaced by the main thread
            state["error"] = exc

    thread = threading.Thread(target=worker, name="voice-asr-preload", daemon=True)
    thread.start()
    return thread, state


def _finish_asr_backend_preload(thread: threading.Thread | None, state: dict[str, Any]) -> None:
    if thread is not None and thread.is_alive():
        thread.join()
    error = state.get("error")
    if error is not None:
        raise error


def _append_fast_demo_reminder(path: str | None, record: dict[str, Any]) -> None:
    if not path:
        return
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    try:
        existing = json.loads(target.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        existing = {}
    items = existing.get("items") if isinstance(existing, dict) and isinstance(existing.get("items"), list) else []
    items.append(record)
    payload = {
        "schema_version": "xiaoan.fast_demo_reminders.v1",
        "updated_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "items": items,
    }
    tmp = target.with_suffix(target.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(target)


def _maybe_schedule_openclaw_reminder_fallback(
    output: dict,
    transcript: str,
    *,
    reminders_path: str | None,
    send_to_robot: bool,
    allow_motion: bool,
    gateway_url: str,
) -> dict[str, Any] | None:
    capture = _openclaw_capture(output)
    if not _is_local_reminder_fallback_capture(capture):
        return None

    reminder = parse_reminder_due_at(transcript)
    has_capture_due_at = False
    if isinstance(capture, dict):
        due_at = str(capture.get("due_at") or "").strip()
        if due_at:
            reminder["due_at"] = due_at
            has_capture_due_at = True
        title = str(capture.get("title") or "").strip()
        if title:
            reminder["title"] = title
    if not has_capture_due_at and not _has_explicit_reminder_time(reminder):
        return None

    decision = {
        "intent": "capture_reminder",
        "reply_text": output.get("reply_text") or output.get("display_text"),
        "trigger": {"reminder": reminder},
    }
    record = build_reminder_record(
        decision,
        transcript=transcript,
        send_to_robot=send_to_robot,
        allow_motion=allow_motion,
        gateway_url=gateway_url,
    )
    if record is None:
        return None

    record["source"] = "openclaw_reminder_fallback"
    record["openclaw_capture"] = capture
    _append_fast_demo_reminder(reminders_path, record)
    output["scheduled_reminder"] = record
    output["local_reminder_fallback"] = {
        "ok": True,
        "reason": "openclaw_missing_cron_tool",
        "reminders_path": reminders_path,
        "reminder_id": record.get("id"),
        "due_at": record.get("due_at"),
    }
    return record


def _openclaw_capture(output: dict) -> dict[str, Any] | None:
    raw = output.get("openclaw_raw")
    if isinstance(raw, dict) and isinstance(raw.get("capture"), dict):
        return raw["capture"]
    result = output.get("openclaw_result")
    if isinstance(result, dict):
        nested_raw = result.get("openclaw_raw")
        if isinstance(nested_raw, dict) and isinstance(nested_raw.get("capture"), dict):
            return nested_raw["capture"]
    return None


def _is_local_reminder_fallback_capture(capture: dict[str, Any] | None) -> bool:
    if not isinstance(capture, dict):
        return False
    if str(capture.get("kind") or "").strip().lower() not in {"reminder", "alarm"}:
        return False
    if str(capture.get("status") or "").strip().lower() != "captured":
        return False
    if str(capture.get("source_of_truth") or "") == "base_station_local_reminder_fallback":
        return True
    metadata = capture.get("metadata")
    return (
        isinstance(metadata, dict)
        and str(metadata.get("fallback_reason") or "") == "openclaw_missing_cron_tool"
    )


def _has_explicit_reminder_time(reminder: dict[str, Any]) -> bool:
    if not isinstance(reminder, dict):
        return False
    confidence = reminder.get("time_parse_confidence")
    try:
        score = float(confidence)
    except (TypeError, ValueError):
        score = 0.0
    return score >= 0.5 and str(reminder.get("time_text") or "") != "默认1分钟后"


def prewarm_asr_model(
    *,
    asr_backend: str = "sensevoice",
    asr_model_path: str | None = "base_station/models/sensevoice-small",
    asr_device: str = "cpu",
    asr_language: str | None = None,
    asr_use_itn: bool = True,
    audio_output_dir: str = "runtime/voice_runtime_audio",
) -> dict:
    started = time.monotonic()
    if asr_backend != "sensevoice":
        return {
            "ok": True,
            "skipped": True,
            "backend": asr_backend,
            "reason": "prewarm_only_required_for_sensevoice",
            "duration_ms": int((time.monotonic() - started) * 1000),
        }

    wav_path = Path(audio_output_dir) / "prewarm_silence.wav"
    _write_silence_wav(wav_path)
    backend = SenseVoiceASRBackend(
        model_dir=asr_model_path,
        device=asr_device,
        language=asr_language,
        use_itn=asr_use_itn,
    )
    result = backend.transcribe(
        {
            "source": "prewarm",
            "audio_path": str(wav_path),
            "sample_rate": 16000,
            "duration_ms": 250,
            "channels": 1,
        }
    )
    return {
        "ok": True,
        "backend": "sensevoice",
        "model_path": asr_model_path,
        "device": asr_device,
        "language": asr_language,
        "audio_path": str(wav_path),
        "asr": result,
        "duration_ms": int((time.monotonic() - started) * 1000),
    }


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
    parser.add_argument("--prewarm-asr", action="store_true", help="Load the configured ASR model once and exit.")
    parser.add_argument("--device", default=None, help="Local microphone device index, id, or name substring.")
    parser.add_argument("--duration", type=float, default=5.0, help="Fixed local_mic capture window in seconds.")
    parser.add_argument(
        "--capture-mode",
        choices=sorted(CAPTURE_MODES),
        default="fixed_window",
        help="Use fixed windows or record one utterance until microphone recognition is switched off.",
    )
    parser.add_argument(
        "--work-mode-gated",
        action="store_true",
        help="Honor XIAOAN_WORK_MODE_STATE_PATH as a microphone recognition gate.",
    )
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
    parser.add_argument(
        "--decision-mode",
        choices=sorted(DECISION_MODES),
        default="openclaw",
        help="Use OpenClaw routing or Integration Console local Fast Demo decisions after ASR.",
    )
    parser.add_argument(
        "--local-demo-link",
        choices=["fast1", "fast3"],
        default="fast1",
        help="Fast Demo voice link identity when --decision-mode local_demo is used.",
    )
    parser.add_argument(
        "--local-demo-send-to-robot",
        action="store_true",
        help="Send Fast Demo expression/TTS commands to the robot after local decision.",
    )
    parser.add_argument(
        "--local-demo-allow-motion",
        action="store_true",
        help="Allow Fast Demo motion steps. Motion parameters remain fixed and conservative.",
    )
    parser.add_argument(
        "--local-demo-reminders-path",
        default=None,
        help="Append Fast Demo reminder records to this JSON file when reminder intent is captured.",
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
    if args.prewarm_asr:
        result = prewarm_asr_model(
            asr_backend=args.asr_backend,
            asr_model_path=args.asr_model_path,
            asr_device=args.asr_device,
            asr_language=args.asr_language,
            asr_use_itn=args.asr_use_itn,
            audio_output_dir=args.audio_output_dir,
        )
        print(json.dumps(result, ensure_ascii=False, indent=2))
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
            decision_mode=args.decision_mode,
            local_demo_link=args.local_demo_link,
            local_demo_send_to_robot=args.local_demo_send_to_robot,
            local_demo_allow_motion=args.local_demo_allow_motion,
            local_demo_reminders_path=args.local_demo_reminders_path,
            capture_mode=args.capture_mode,
            work_mode_gated=args.work_mode_gated,
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
        decision_mode=args.decision_mode,
        local_demo_link=args.local_demo_link,
        local_demo_send_to_robot=args.local_demo_send_to_robot,
        local_demo_allow_motion=args.local_demo_allow_motion,
        local_demo_reminders_path=args.local_demo_reminders_path,
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
