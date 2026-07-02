#!/usr/bin/env python3
"""Demo 1: base-station USB mic -> ASR transcript -> local Agent screen."""

from __future__ import annotations

import argparse
import asyncio
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import html
import json
from pathlib import Path
import re
import shutil
import subprocess
import sys
import threading
import time
from typing import Any
import wave


REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from base_station.monitor.asr_runtime import run_once as run_asr_once
from agent.core.gateway import RobotGateway


DEFAULT_RUNTIME_DIR = REPO_ROOT / "runtime"
DEFAULT_STATE_PATH = DEFAULT_RUNTIME_DIR / "demo1_transcript.json"
DEFAULT_TEXT_PATH = DEFAULT_RUNTIME_DIR / "demo1_transcript.txt"
DEFAULT_CONTEXT_PATH = DEFAULT_RUNTIME_DIR / "demo1_openclaw_context.json"
DEFAULT_PLAN_PATH = DEFAULT_RUNTIME_DIR / "demo1_action_plan.json"
DEFAULT_LOG_PATH = DEFAULT_RUNTIME_DIR / "demo1_transcript.log.jsonl"
DEFAULT_AUDIO_DIR = DEFAULT_RUNTIME_DIR / "demo1_audio"
DEFAULT_SCREEN_URL = "http://127.0.0.1:8766"
DEMO_TITLE = "小安 Demo 1：基站麦克风语音识别"


def now_iso() -> str:
    return datetime.now().replace(microsecond=0).isoformat()


def build_state(
    *,
    status: str,
    transcript: str = "",
    source: str | None = None,
    audio_device: str | None = None,
    audio_device_index: int | str | None = None,
    audio_path: str | None = None,
    asr_backend: str | None = None,
    error: str | None = None,
    details: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "title": DEMO_TITLE,
        "status": status,
        "transcript": transcript,
        "source": source,
        "timestamp": now_iso(),
        "audio_device": audio_device,
        "audio_device_index": audio_device_index,
        "audio_path": audio_path,
        "asr_backend": asr_backend,
        "error": error,
        "details": details or {},
    }


def write_state(path: str | Path, state: dict[str, Any]) -> dict[str, Any]:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(state, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return state


def write_transcript_text(path: str | Path, transcript: str) -> Path:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(transcript.strip() + "\n", encoding="utf-8")
    return target


def write_json_artifact(path: str | Path, payload: dict[str, Any]) -> Path:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return target


def append_log(path: str | Path, state: dict[str, Any]) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(state, ensure_ascii=False, sort_keys=True) + "\n")


def update_state(
    state_path: str | Path,
    log_path: str | Path,
    **kwargs: Any,
) -> dict[str, Any]:
    state = build_state(**kwargs)
    write_state(state_path, state)
    append_log(log_path, state)
    return state


def load_state(path: str | Path) -> dict[str, Any]:
    target = Path(path)
    if not target.exists():
        return build_state(status="idle")
    try:
        return json.loads(target.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return build_state(status="error", error=f"Failed to load demo state: {exc}")


def import_pyaudio():
    try:
        import pyaudio  # type: ignore
    except ImportError as exc:
        raise RuntimeError(
            "PyAudio is required for USB microphone recording. "
            "Install base_station/requirements.txt, or use --mock-text for fallback."
        ) from exc
    return pyaudio


def _pyaudio_input_devices() -> list[dict[str, Any]]:
    pyaudio = import_pyaudio()
    audio = pyaudio.PyAudio()
    devices: list[dict[str, Any]] = []
    try:
        for index in range(audio.get_device_count()):
            info = audio.get_device_info_by_index(index)
            if int(info.get("maxInputChannels") or 0) <= 0:
                continue
            devices.append(
                {
                    "backend": "pyaudio",
                    "index": int(info["index"]),
                    "device_id": str(info["index"]),
                    "name": str(info.get("name") or f"input-{index}"),
                    "max_input_channels": int(info.get("maxInputChannels") or 0),
                    "default_sample_rate": float(info.get("defaultSampleRate") or 0),
                }
            )
    finally:
        audio.terminate()
    return devices


def parse_arecord_devices(output: str) -> list[dict[str, Any]]:
    devices: list[dict[str, Any]] = []
    pattern = re.compile(
        r"card\s+(?P<card>\d+):\s+(?P<card_id>[^\[]+)\[(?P<card_name>[^\]]+)\],\s+"
        r"device\s+(?P<device>\d+):\s+(?P<device_id>[^\[]+)\[(?P<device_name>[^\]]+)\]"
    )
    for line in output.splitlines():
        match = pattern.search(line)
        if not match:
            continue
        card = int(match.group("card"))
        device = int(match.group("device"))
        card_name = match.group("card_name").strip()
        device_name = match.group("device_name").strip()
        devices.append(
            {
                "backend": "arecord",
                "index": f"hw:{card},{device}",
                "device_id": f"plughw:{card},{device}",
                "hardware_id": f"hw:{card},{device}",
                "card": card,
                "device": device,
                "name": f"{card_name} {device_name}".strip(),
                "max_input_channels": 1,
                "default_sample_rate": 16000.0,
            }
        )
    return devices


def _arecord_input_devices() -> list[dict[str, Any]]:
    if shutil.which("arecord") is None:
        return []
    result = subprocess.run(["arecord", "-l"], text=True, capture_output=True, check=False)
    if result.returncode != 0:
        raise RuntimeError(f"arecord -l failed: {result.stderr.strip() or result.stdout.strip()}")
    return parse_arecord_devices(result.stdout)


def list_input_devices() -> list[dict[str, Any]]:
    devices: list[dict[str, Any]] = []
    try:
        devices.extend(_pyaudio_input_devices())
    except RuntimeError:
        pass
    try:
        devices.extend(_arecord_input_devices())
    except RuntimeError:
        if not devices:
            raise
    if devices:
        return devices
    raise RuntimeError(
        "No audio input devices found through PyAudio or arecord. "
        "Check the USB microphone connection, or use --mock-text for fallback."
    )


def choose_input_device(devices: list[dict[str, Any]], requested: str | None = None) -> dict[str, Any]:
    if not devices:
        raise RuntimeError("No audio input devices found. Check that the USB microphone is connected.")

    if requested:
        requested_text = str(requested).strip()
        lowered = requested_text.lower()
        for device in devices:
            if lowered in {
                str(device.get("index")).lower(),
                str(device.get("device_id")).lower(),
                str(device.get("hardware_id")).lower(),
            }:
                return device

        if requested_text.isdigit():
            requested_index = int(requested_text)
            for device in devices:
                if isinstance(device.get("index"), int) and int(device["index"]) == requested_index:
                    return device
                if int(device.get("card") or -1) == requested_index:
                    return device
            raise RuntimeError(f"Audio input device index not found: {requested_index}")

        matches = [
            device
            for device in devices
            if lowered in str(device["name"]).lower()
        ]
        if matches:
            return matches[0]
        raise RuntimeError(f"Audio input device name not found: {requested_text}")

    preferred_markers = ("usb", "microphone", "mic", "麦克风")
    preferred_devices: list[dict[str, Any]] = []
    for device in devices:
        name = str(device["name"]).lower()
        if any(marker in name for marker in preferred_markers):
            preferred_devices.append(device)
    for device in preferred_devices:
        if device.get("backend") == "arecord":
            return device
    if preferred_devices:
        return preferred_devices[0]
    return devices[0]


def print_devices(devices: list[dict[str, Any]]) -> None:
    if not devices:
        print("No audio input devices found.")
        return
    for device in devices:
        print(
            f"{device['index']}: {device['name']} "
            f"(backend={device.get('backend')}, inputs={device['max_input_channels']}, "
            f"default_rate={device['default_sample_rate']:.0f})"
        )


def record_wav(
    *,
    device: dict[str, Any],
    output_path: str | Path,
    duration_seconds: float,
    sample_rate: int = 16000,
    channels: int = 1,
    frames_per_buffer: int = 1024,
) -> Path:
    if device.get("backend") == "arecord":
        return record_wav_arecord(
            device_id=str(device["device_id"]),
            output_path=output_path,
            duration_seconds=duration_seconds,
            sample_rate=sample_rate,
            channels=channels,
        )

    pyaudio = import_pyaudio()
    audio = pyaudio.PyAudio()
    stream = None
    frames: list[bytes] = []
    target = Path(output_path)
    target.parent.mkdir(parents=True, exist_ok=True)
    try:
        stream = audio.open(
            format=pyaudio.paInt16,
            channels=channels,
            rate=sample_rate,
            input=True,
            input_device_index=int(device["index"]),
            frames_per_buffer=frames_per_buffer,
        )
        chunks = max(1, int(sample_rate / frames_per_buffer * duration_seconds))
        for _ in range(chunks):
            frames.append(stream.read(frames_per_buffer, exception_on_overflow=False))
    finally:
        if stream is not None:
            stream.stop_stream()
            stream.close()
        audio.terminate()

    with wave.open(str(target), "wb") as wav:
        wav.setnchannels(channels)
        wav.setsampwidth(2)
        wav.setframerate(sample_rate)
        wav.writeframes(b"".join(frames))
    return target


def record_wav_arecord(
    *,
    device_id: str,
    output_path: str | Path,
    duration_seconds: float,
    sample_rate: int,
    channels: int,
) -> Path:
    if shutil.which("arecord") is None:
        raise RuntimeError("arecord is not installed; cannot record without PyAudio.")
    target = Path(output_path)
    target.parent.mkdir(parents=True, exist_ok=True)
    seconds = max(1, int(round(duration_seconds)))
    command = [
        "arecord",
        "-D",
        device_id,
        "-f",
        "S16_LE",
        "-r",
        str(sample_rate),
        "-c",
        str(channels),
        "-d",
        str(seconds),
        str(target),
    ]
    result = subprocess.run(command, text=True, capture_output=True, check=False)
    if result.returncode != 0:
        raise RuntimeError(f"arecord failed: {result.stderr.strip() or result.stdout.strip()}")
    return target


async def transcribe_audio_file(args: argparse.Namespace, audio_path: Path) -> dict[str, Any]:
    trim_path = audio_path.with_name(f"{audio_path.stem}.trim.wav") if args.trim_speech else None
    return await run_asr_once(
        source="audio_file",
        audio_path=str(audio_path),
        vad_backend=args.vad_backend,
        vad_threshold=args.vad_threshold,
        asr_backend=args.asr_backend,
        asr_model_path=args.asr_model_path,
        device=args.asr_device,
        no_agent=True,
        trim_speech=args.trim_speech,
        speech_trim_path=str(trim_path) if trim_path else None,
        speech_trim_threshold=args.speech_trim_threshold,
        speech_trim_padding_ms=args.speech_trim_padding_ms,
    )


def build_openclaw_context(
    *,
    transcript: str,
    source: str,
    audio_device: str | None = None,
    audio_path: str | None = None,
    asr_output: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "event_type": "asr.transcript",
        "source": source,
        "timestamp": now_iso(),
        "payload": {
            "text": transcript,
            "source": source,
            "audio_device": audio_device,
            "audio_path": audio_path,
        },
        "robot_capabilities": [
            "display.expression",
            "motion.execute",
            "audio.play_local",
        ],
        "available_local_sounds": ["care_01"],
        "asr_output": asr_output or {},
    }


def build_rule_action_plan(transcript: str) -> dict[str, Any]:
    text = transcript.strip()
    fatigue_keywords = ("累", "困", "疲劳", "疲勞", "低落", "烦", "煩", "陪陪")
    approach_keywords = ("过来", "過來", "来一下", "過來一下", "小安")
    should_care = any(keyword in text for keyword in fatigue_keywords)
    should_approach = any(keyword in text for keyword in approach_keywords)

    if not should_care and not should_approach:
        return {
            "route": "demo1_rule_noop",
            "reason": "no_demo_keyword",
            "handled": False,
            "actions": [],
        }

    actions = [
        {
            "name": "display.expression",
            "arguments": {
                "expression": "caring" if should_care else "happy",
                "duration_ms": 3000,
            },
        },
        {
            "name": "motion.execute",
            "arguments": {
                "action": "move_out_of_dock",
                "params": {"speed": 0.56, "distance_cm": 10.0},
                "timeout_ms": 1200,
            },
        },
    ]
    if should_care:
        actions.append(
            {
                "name": "motion.execute",
                "arguments": {
                    "action": "turn",
                    "params": {"speed": 0.52, "angle_deg": -20},
                    "timeout_ms": 700,
                },
            }
        )
        actions.append(
            {
                "name": "audio.play_local",
                "arguments": {
                    "audio_id": "care_01",
                    "sound": "care_01",
                    "volume": 0.7,
                },
            }
        )

    return {
        "route": "demo1_rule_care" if should_care else "demo1_rule_approach",
        "reason": "fatigue_keyword" if should_care else "approach_keyword",
        "handled": True,
        "actions": actions,
    }


async def send_action_plan_to_agent(plan: dict[str, Any], gateway_url: str) -> dict[str, Any]:
    gateway = RobotGateway(url=gateway_url)
    results: list[dict[str, Any]] = []
    for index, action in enumerate(plan.get("actions") or []):
        name = str(action.get("name") or "")
        arguments = action.get("arguments") if isinstance(action.get("arguments"), dict) else {}
        result: dict[str, Any] = {
            "index": index,
            "name": name,
            "arguments": arguments,
            "ok": False,
        }
        try:
            if name == "display.expression":
                result["ack"] = await gateway.send_expression(
                    str(arguments.get("expression") or "caring"),
                    duration_ms=int(arguments.get("duration_ms") or 3000),
                    loop=bool(arguments.get("loop", False)),
                )
            elif name == "motion.execute":
                result["ack"] = await gateway.send_motion(
                    str(arguments.get("action") or "move_out_of_dock"),
                    params=arguments.get("params") if isinstance(arguments.get("params"), dict) else {},
                    timeout_ms=int(arguments.get("timeout_ms") or 1200),
                )
            elif name == "audio.play_local":
                result["ack"] = await gateway.send_local_audio(
                    str(arguments.get("audio_id") or arguments.get("sound") or "care_01"),
                )
            else:
                result["error"] = f"Unsupported demo action: {name}"
        except Exception as exc:
            result["error"] = str(exc)
        else:
            result["ok"] = True
        results.append(result)

    return {
        "attempted": bool(plan.get("actions")),
        "ok": bool(results) and all(item.get("ok") for item in results),
        "gateway_url": gateway_url,
        "results": results,
    }


async def route_transcript_if_requested(
    args: argparse.Namespace,
    *,
    transcript: str,
    transcript_source: str,
    audio_device: str | None = None,
    audio_path: str | None = None,
    asr_output: dict[str, Any] | None = None,
) -> dict[str, Any]:
    context = build_openclaw_context(
        transcript=transcript,
        source=transcript_source,
        audio_device=audio_device,
        audio_path=audio_path,
        asr_output=asr_output,
    )
    plan = build_rule_action_plan(transcript)
    write_json_artifact(args.context_path, context)
    write_json_artifact(args.plan_path, plan)

    route_result: dict[str, Any] = {
        "enabled": bool(args.route_agent),
        "context_path": str(Path(args.context_path)),
        "plan_path": str(Path(args.plan_path)),
        "context": context,
        "action_plan": plan,
        "agent_send": None,
    }
    if args.route_agent:
        route_result["agent_send"] = await send_action_plan_to_agent(
            plan,
            gateway_url=args.gateway_url,
        )
    return route_result


def make_screen_html(state: dict[str, Any]) -> bytes:
    status = html.escape(str(state.get("status") or "idle"))
    transcript = html.escape(str(state.get("transcript") or "等待识别..."))
    source = html.escape(str(state.get("source") or "--"))
    timestamp = html.escape(str(state.get("timestamp") or "--"))
    device = html.escape(str(state.get("audio_device") or "--"))
    error = html.escape(str(state.get("error") or ""))
    body = f"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{DEMO_TITLE}</title>
  <style>
    :root {{
      color-scheme: dark;
      font-family: "Segoe UI", "Microsoft YaHei", Arial, sans-serif;
      background: #101416;
      color: #f5f7f8;
    }}
    body {{
      margin: 0;
      min-height: 100vh;
      display: grid;
      place-items: center;
      background: #101416;
    }}
    main {{
      width: min(980px, calc(100vw - 48px));
    }}
    h1 {{
      margin: 0 0 28px;
      font-size: 42px;
      font-weight: 800;
      letter-spacing: 0;
    }}
    .status {{
      display: inline-flex;
      padding: 8px 14px;
      border: 1px solid #4d6b73;
      border-radius: 6px;
      color: #9ee7d8;
      font-size: 22px;
      font-weight: 700;
    }}
    .transcript {{
      margin: 28px 0;
      padding: 28px 0;
      border-top: 1px solid #2d3a3d;
      border-bottom: 1px solid #2d3a3d;
      font-size: 46px;
      line-height: 1.35;
      font-weight: 800;
      word-break: break-word;
    }}
    dl {{
      display: grid;
      grid-template-columns: 150px 1fr;
      gap: 12px 20px;
      font-size: 20px;
      color: #cbd7da;
    }}
    dt {{
      color: #88a1a8;
    }}
    dd {{
      margin: 0;
      word-break: break-word;
    }}
    .error {{
      color: #ffb4a8;
      font-weight: 700;
    }}
  </style>
</head>
<body>
  <main>
    <h1>{DEMO_TITLE}</h1>
    <div class="status">状态：<span id="status">{status}</span></div>
    <section class="transcript">最近识别内容：<span id="transcript">{transcript}</span></section>
    <dl>
      <dt>来源</dt><dd id="source">{source}</dd>
      <dt>时间</dt><dd id="timestamp">{timestamp}</dd>
      <dt>音频设备</dt><dd id="device">{device}</dd>
      <dt>错误</dt><dd id="error" class="error">{error}</dd>
    </dl>
  </main>
  <script>
    async function refresh() {{
      try {{
        const response = await fetch('/api/demo1/transcript', {{cache: 'no-store'}});
        const state = await response.json();
        document.getElementById('status').textContent = state.status || 'idle';
        document.getElementById('transcript').textContent = state.transcript || '等待识别...';
        document.getElementById('source').textContent = state.source || '--';
        document.getElementById('timestamp').textContent = state.timestamp || '--';
        document.getElementById('device').textContent = state.audio_device || '--';
        document.getElementById('error').textContent = state.error || '';
      }} catch (err) {{
        document.getElementById('error').textContent = String(err);
      }}
    }}
    setInterval(refresh, 1000);
    refresh();
  </script>
</body>
</html>
"""
    return body.encode("utf-8")


def make_handler(state_path: Path):
    class Demo1ScreenHandler(BaseHTTPRequestHandler):
        def log_message(self, format: str, *args: Any) -> None:
            return None

        def do_GET(self) -> None:
            if self.path in {"/", "/demo1"}:
                self._write(200, "text/html; charset=utf-8", make_screen_html(load_state(state_path)))
                return
            if self.path == "/api/demo1/transcript":
                payload = json.dumps(load_state(state_path), ensure_ascii=False, indent=2).encode("utf-8")
                self._write(200, "application/json; charset=utf-8", payload)
                return
            self._write(404, "text/plain; charset=utf-8", b"not found")

        def _write(self, status: int, content_type: str, payload: bytes) -> None:
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)

    return Demo1ScreenHandler


def start_screen_server(host: str, port: int, state_path: Path) -> ThreadingHTTPServer:
    server = ThreadingHTTPServer((host, int(port)), make_handler(state_path))
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server


def audio_output_path(audio_dir: Path) -> Path:
    return audio_dir / f"demo1_usb_mic_{datetime.now().strftime('%Y%m%d_%H%M%S')}.wav"


def recording_sample_rate(device: dict[str, Any], requested_sample_rate: int) -> int:
    if device.get("backend") != "pyaudio":
        return requested_sample_rate
    default_rate = int(float(device.get("default_sample_rate") or 0))
    return default_rate if default_rate > 0 else requested_sample_rate


async def run_demo(args: argparse.Namespace) -> int:
    state_path = Path(args.state_path)
    text_path = Path(args.text_path)
    context_path = Path(args.context_path)
    plan_path = Path(args.plan_path)
    log_path = Path(args.log_path)
    audio_dir = Path(args.audio_dir)
    server = None

    if args.list_devices:
        print_devices(list_input_devices())
        return 0

    update_state(
        state_path,
        log_path,
        status="idle",
        details={
            "screen_url": args.screen_url,
            "text_path": str(text_path),
            "context_path": str(context_path),
            "plan_path": str(plan_path),
            "route_agent": args.route_agent,
        },
    )
    if not args.no_screen:
        server = start_screen_server(args.host, args.port, state_path)
        print(f"Demo 1 screen: {args.screen_url}")

    try:
        if args.mock_text is not None:
            write_transcript_text(text_path, args.mock_text)
            route_result = await route_transcript_if_requested(
                args,
                transcript=args.mock_text,
                transcript_source="mock",
            )
            state = update_state(
                state_path,
                log_path,
                status="done",
                transcript=args.mock_text,
                source="mock",
                asr_backend="mock",
                details={
                    "mock_reason": "explicit --mock-text fallback",
                    "text_path": str(text_path),
                    "route_result": route_result,
                },
            )
            print(json.dumps(state, ensure_ascii=False, indent=2))
            return 0

        devices = list_input_devices()
        selected = choose_input_device(devices, args.device)
        device_name = str(selected["name"])
        device_index = selected.get("index")
        sample_rate = recording_sample_rate(selected, args.sample_rate)
        wav_path = audio_output_path(audio_dir)

        update_state(
            state_path,
            log_path,
            status="listening",
            source="asr",
            audio_device=device_name,
            audio_device_index=device_index,
            audio_path=str(wav_path),
            asr_backend=args.asr_backend,
            details={
                "duration_seconds": args.duration,
                "sample_rate": sample_rate,
                "requested_sample_rate": args.sample_rate,
                "audio_backend": selected.get("backend"),
                "audio_device_id": selected.get("device_id"),
                "text_path": str(text_path),
                "route_agent": args.route_agent,
            },
        )
        print(f"Recording {args.duration:.1f}s from [{device_index}] {device_name}")
        record_wav(
            device=selected,
            output_path=wav_path,
            duration_seconds=args.duration,
            sample_rate=sample_rate,
            channels=1,
        )

        update_state(
            state_path,
            log_path,
            status="transcribing",
            source="asr",
            audio_device=device_name,
            audio_device_index=device_index,
            audio_path=str(wav_path),
            asr_backend=args.asr_backend,
        )
        output = await transcribe_audio_file(args, wav_path)
        transcript = str(output.get("text") or "").strip()
        if not transcript:
            raise RuntimeError(f"ASR returned no transcript: {json.dumps(output, ensure_ascii=False)}")

        write_transcript_text(text_path, transcript)
        update_state(
            state_path,
            log_path,
            status="routing" if args.route_agent else "planning",
            transcript=transcript,
            source="asr" if args.asr_backend == "sensevoice" else "mock",
            audio_device=device_name,
            audio_device_index=device_index,
            audio_path=str(wav_path),
            asr_backend=args.asr_backend,
            details={
                "text_path": str(text_path),
                "context_path": str(context_path),
                "plan_path": str(plan_path),
                "route_agent": args.route_agent,
            },
        )
        route_result = await route_transcript_if_requested(
            args,
            transcript=transcript,
            transcript_source="asr" if args.asr_backend == "sensevoice" else "mock",
            audio_device=device_name,
            audio_path=str(wav_path),
            asr_output=output,
        )
        state = update_state(
            state_path,
            log_path,
            status="done",
            transcript=transcript,
            source="asr" if args.asr_backend == "sensevoice" else "mock",
            audio_device=device_name,
            audio_device_index=device_index,
            audio_path=str(wav_path),
            asr_backend=args.asr_backend,
            details={
                "asr_output": output,
                "text_path": str(text_path),
                "route_result": route_result,
            },
        )
        print(json.dumps(state, ensure_ascii=False, indent=2))
        return 0
    except Exception as exc:
        message = str(exc)
        if "SenseVoice" in message or "funasr" in message or "ASR" in message:
            message = f"ASR backend unavailable: {message}. Use --mock-text to verify the screen path."
        state = update_state(
            state_path,
            log_path,
            status="error",
            source="asr",
            asr_backend=args.asr_backend,
            error=message,
        )
        print(json.dumps(state, ensure_ascii=False, indent=2), file=sys.stderr)
        return 1
    finally:
        if server is not None and args.once:
            server.shutdown()
            server.server_close()
        elif server is not None:
            print("Press Ctrl+C to stop the Demo 1 screen server.")
            try:
                while True:
                    time.sleep(1)
            except KeyboardInterrupt:
                server.shutdown()
                server.server_close()


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=DEMO_TITLE)
    parser.add_argument("--list-devices", action="store_true", help="List audio input devices and exit.")
    parser.add_argument("--device", default=None, help="Audio input device index or name substring. Defaults to USB mic.")
    parser.add_argument("--duration", type=float, default=5.0, help="Recording window in seconds.")
    parser.add_argument("--sample-rate", type=int, default=16000)
    parser.add_argument("--asr-backend", choices=["sensevoice", "fake"], default="sensevoice")
    parser.add_argument("--asr-model-path", default="base_station/models/sensevoice-small")
    parser.add_argument("--asr-device", default="cpu")
    parser.add_argument("--vad-backend", choices=["fake", "energy", "silero"], default="energy")
    parser.add_argument("--vad-threshold", type=float, default=0.003)
    parser.add_argument("--trim-speech", action="store_true", default=True)
    parser.add_argument("--no-trim-speech", dest="trim_speech", action="store_false")
    parser.add_argument("--speech-trim-threshold", type=float, default=0.003)
    parser.add_argument("--speech-trim-padding-ms", type=int, default=250)
    parser.add_argument("--mock-text", default=None, help="Fallback transcript. Does not pretend to be real ASR.")
    parser.add_argument("--route-agent", action="store_true", help="Build a context/action plan and send it through /agent.")
    parser.add_argument("--gateway-url", default="ws://127.0.0.1:8765/agent", help="Base station /agent URL.")
    parser.add_argument("--state-path", default=str(DEFAULT_STATE_PATH))
    parser.add_argument("--text-path", default=str(DEFAULT_TEXT_PATH), help="Plain transcript text output path.")
    parser.add_argument("--context-path", default=str(DEFAULT_CONTEXT_PATH), help="OpenClaw/context input artifact path.")
    parser.add_argument("--plan-path", default=str(DEFAULT_PLAN_PATH), help="Demo action plan artifact path.")
    parser.add_argument("--log-path", default=str(DEFAULT_LOG_PATH))
    parser.add_argument("--audio-dir", default=str(DEFAULT_AUDIO_DIR))
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8766)
    parser.add_argument("--no-screen", action="store_true", help="Do not start the local screen HTTP server.")
    parser.add_argument("--once", action="store_true", help="Exit after one recording/mock cycle instead of keeping screen open.")
    args = parser.parse_args(argv)
    display_host = "localhost" if args.host in {"127.0.0.1", "0.0.0.0"} else args.host
    args.screen_url = f"http://{display_host}:{args.port}"
    return args


def main(argv: list[str] | None = None) -> int:
    try:
        return asyncio.run(run_demo(parse_args(argv)))
    except KeyboardInterrupt:
        raise
    except (RuntimeError, ValueError, OSError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
