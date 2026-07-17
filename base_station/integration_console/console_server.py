"""Standard-library Integration Console for DK-2500 bring-up.

Run from the repository root:
    python -m base_station.integration_console.console_server --host 0.0.0.0 --port 8090
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import re
import signal
import socket
import subprocess
import sys
import threading
import time
import uuid
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Callable
from urllib.parse import unquote, urlparse, urlsplit

from base_station.integration_console.fast_demo_brain import (
    DANCE_INTRO_TEXT,
    POST_MOTION_TTS_SETTLE_SECONDS,
    build_reminder_due_decision,
    decide_visual,
    decide_voice,
)
from base_station.integration_console.story_demo import (
    STORY_SCHEMA_VERSION,
    advance_story_state,
    build_story_state,
    get_story_node,
    is_story_start_request,
    resolve_story_choice,
    stop_story_state,
    story_state_summary,
)

DEFAULT_RUNTIME_DIR = Path("runtime")
DEFAULT_STATIC_DIR = Path(__file__).with_name("static")
DEFAULT_WS_URL = "ws://127.0.0.1:8765/agent"
DEFAULT_OPENCLAW_URL = "ws://127.0.0.1:18789"
DEFAULT_OPENCLAW_WORKSPACE = Path.home() / ".openclaw" / "workspace-xiaoan-runtime"
DEFAULT_QWEN_VL_MODEL_PATH = "base_station/models/Qwen2.5-VL-3B-OV-int4"
OPENCLAW_DASHBOARD_SCHEMA = "xiaoan.dashboard.v1"
EVENT_LIMIT = 200
STATE_EVENT_LIMIT = 50
AUDIO_COOLDOWN_SECONDS = 2.5
AGENT_ACK_TIMEOUT_SECONDS = 4.0
AGENT_TTS_ACK_TIMEOUT_SECONDS = 75.0
FRESH_IMAGE_MS = 3000
FRESH_AUDIO_MS = 5000
FRESH_VISUAL_MS = 3000
FAST2_AUTO_CARE_COOLDOWN_SECONDS = 20.0
STORY_TTS_MAX_PCM_BYTES = 512_000
MOTION_ACTIONS = {"move_out_of_dock", "move_back_to_dock", "turn", "stop"}
EXPRESSIONS = {
    "happy",
    "sad",
    "caring",
    "tired",
    "thinking",
    "speaking",
    "idle",
    "surprised",
    "sleeping",
}
LOCAL_SOUNDS = {"care_01", "success_ding"}
STANDARD_LINKS = ("link1", "link2", "link3")
FAST_DEMO_LINKS = ("fast1", "fast2", "fast3")
DANCE_KEYWORDS = ("跳舞", "唱歌跳舞", "跳个舞")


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _agent_ack_timeout_seconds(payload: dict[str, Any]) -> float:
    if payload.get("command") == "audio.play_tts":
        return AGENT_TTS_ACK_TIMEOUT_SECONDS
    return AGENT_ACK_TIMEOUT_SECONDS


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _json_bytes(data: Any) -> bytes:
    return json.dumps(data, ensure_ascii=False, indent=2).encode("utf-8")


def _load_json_file(path: Path) -> tuple[dict[str, Any] | None, str | None]:
    try:
        raw = path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return None, "not_found"
    except OSError as exc:
        return None, str(exc)
    if not raw.strip():
        return None, "empty"
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        return None, f"bad_json:{exc.msg}"
    if not isinstance(data, dict):
        return None, "not_object"
    return data, None


def read_ws_state(runtime_dir: str | Path) -> dict[str, Any]:
    path = Path(runtime_dir) / "ws_state.json"
    data, error = _load_json_file(path)
    if data is None:
        return {
            "ok": False,
            "exists": path.exists(),
            "path": str(path),
            "reason": error or "not_found",
            "state": {},
        }
    return {
        "ok": True,
        "exists": True,
        "path": str(path),
        "reason": None,
        "state": data,
    }


def _file_info(path: Path) -> dict[str, Any]:
    try:
        stat = path.stat()
    except OSError:
        return {
            "exists": False,
            "path": str(path),
            "size": 0,
            "updated_at": None,
            "mtime": None,
            "age_ms": None,
        }
    age_ms = int(max(0.0, time.time() - stat.st_mtime) * 1000)
    return {
        "exists": True,
        "path": str(path),
        "size": stat.st_size,
        "updated_at": datetime.fromtimestamp(stat.st_mtime, timezone.utc).isoformat(),
        "mtime": stat.st_mtime,
        "age_ms": age_ms,
    }


def _parse_received_at(item: Any) -> float | None:
    if not isinstance(item, dict):
        return None
    value = item.get("received_at")
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00")).timestamp()
    except ValueError:
        return None


def _parse_iso_timestamp(value: Any) -> float | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00")).timestamp()
    except ValueError:
        return None


def _timestamp_age_ms(value: Any) -> int | None:
    timestamp = _parse_iso_timestamp(value)
    if timestamp is None:
        return None
    return int(max(0.0, time.time() - timestamp) * 1000)


def _iso_timestamp(value: Any) -> float | None:
    return _parse_iso_timestamp(value)


def _fresh(info: dict[str, Any], max_age_ms: int) -> bool:
    return bool(
        info.get("exists")
        and info.get("age_ms") is not None
        and int(info.get("age_ms") or 0) <= max_age_ms
    )


def _step(label: str, ok: bool, detail: Any = None) -> dict[str, Any]:
    return {
        "label": label,
        "ok": bool(ok),
        "detail": detail,
    }


def _tail_lines(text: str, limit: int = 200) -> str:
    lines = text.splitlines()
    return "\n".join(lines[-limit:])


def _sanitize_payload(payload: Any) -> Any:
    if isinstance(payload, dict):
        sanitized: dict[str, Any] = {}
        for key, value in payload.items():
            lower = str(key).lower()
            if any(secret in lower for secret in ("token", "secret", "key", "password")):
                sanitized[key] = "[redacted]"
            elif lower in {"data", "audio", "video", "raw", "jpeg", "pcm"}:
                sanitized[key] = f"[omitted:{type(value).__name__}]"
            else:
                sanitized[key] = _sanitize_payload(value)
        return sanitized
    if isinstance(payload, list):
        return [_sanitize_payload(item) for item in payload[:20]]
    if isinstance(payload, str) and len(payload) > 500:
        return payload[:500] + "...[truncated]"
    return payload


def _atomic_write_json(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
    os.replace(tmp, path)


class IntegrationConsoleApp:
    def __init__(
        self,
        *,
        host: str = "127.0.0.1",
        port: int = 8090,
        ws_url: str = DEFAULT_WS_URL,
        runtime_dir: str | Path = DEFAULT_RUNTIME_DIR,
        static_dir: str | Path = DEFAULT_STATIC_DIR,
        openclaw_url: str = DEFAULT_OPENCLAW_URL,
        openclaw_workspace: str | Path = DEFAULT_OPENCLAW_WORKSPACE,
        command_sender: Callable[[dict[str, Any]], dict[str, Any]] | None = None,
        prewarm_voice: bool = False,
        prewarm_fast_demo_tts: bool = False,
        prewarm_fast2_visual: bool = False,
    ):
        self.host = host
        self.port = int(port)
        self.ws_url = ws_url
        self.runtime_dir = Path(runtime_dir)
        self.static_dir = Path(static_dir)
        self.openclaw_url = openclaw_url
        self.openclaw_workspace = Path(openclaw_workspace).expanduser()
        self.started_at = time.time()
        self.last_audio_sent_at = 0.0
        self.command_sender = command_sender
        self.link_processes: dict[str, subprocess.Popen[Any]] = {}
        self.fast_demo_options: dict[str, dict[str, bool]] = {
            link: {"send_to_robot": False, "allow_motion": False}
            for link in FAST_DEMO_LINKS
        }
        self.fast_demo_reminder_lock = threading.Lock()
        self.fast_demo_story_lock = threading.Lock()
        self.fast2_auto_care_lock = threading.Lock()
        self.fast2_auto_care_running = False
        self.fast2_auto_care_last_key: str | None = None
        self.fast2_auto_care_last_started_monotonic = 0.0
        self.fast2_auto_care_last_result: dict[str, Any] | None = None
        self.voice_prewarm_process: subprocess.Popen[Any] | None = None
        self.voice_prewarm_started_at: str | None = None
        self.fast_demo_tts_prewarm_process: subprocess.Popen[Any] | None = None
        self.fast_demo_tts_prewarm_started_at: str | None = None
        if prewarm_voice:
            self.start_voice_prewarm()
        if prewarm_fast_demo_tts:
            self.start_fast_demo_tts_prewarm()
        if prewarm_fast2_visual:
            self.start_fast2_visual_prewarm()

    @property
    def event_dir(self) -> Path:
        return self.runtime_dir / "integration_console"

    @property
    def event_log_path(self) -> Path:
        return self.event_dir / "events.jsonl"

    @property
    def visual_dir(self) -> Path:
        return self.event_dir / "visual"

    @property
    def fast_demo_visual_dir(self) -> Path:
        return self.event_dir / "fast_demo" / "visual"

    @property
    def fast_demo_reminders_path(self) -> Path:
        return self.event_dir / "fast_demo" / "reminders.json"

    @property
    def fast_demo_story_path(self) -> Path:
        return self.event_dir / "fast_demo" / "story_state.json"

    @property
    def fast_demo_story_voice_path(self) -> Path:
        return self.event_dir / "fast_demo" / "story_voice.json"

    @property
    def fast_demo_dance_voice_path(self) -> Path:
        return self.event_dir / "fast_demo" / "dance_voice.json"

    @property
    def process_log_dir(self) -> Path:
        return self.event_dir / "process_logs"

    def link_runtime_dir(self, link: str) -> Path:
        return self.event_dir / link

    def link_voice_output_path(self, link: str) -> Path:
        return self.link_runtime_dir(link) / "latest_voice.json"

    @property
    def openclaw_dashboard_path(self) -> Path:
        return self.openclaw_workspace / "state" / "dashboard.json"

    def health(self) -> dict[str, Any]:
        return {
            "ok": True,
            "current_time": _now_iso(),
            "host": self.host,
            "port": self.port,
            "ws_url": self.ws_url,
            "runtime_dir": str(self.runtime_dir),
            "python_version": sys.version,
            "uptime_sec": round(time.time() - self.started_at, 3),
            "runtime_dir_exists": self.runtime_dir.exists(),
            "ws_state_exists": (self.runtime_dir / "ws_state.json").exists(),
            "latest_jpg_exists": (self.runtime_dir / "latest.jpg").exists(),
            "audio_stats_exists": (self.runtime_dir / "audio_stats.json").exists(),
            "voice_prewarm": self.voice_prewarm_state(),
            "fast_demo_tts_prewarm": self.fast_demo_tts_prewarm_state(),
            "fast2_visual_prewarm": self.fast2_visual_prewarm_state(),
        }

    def audio_stats(self) -> dict[str, Any]:
        path = self.runtime_dir / "audio_stats.json"
        data, error = _load_json_file(path)
        if data is None:
            return {"ok": False, "reason": error or "not_found", "path": str(path)}
        return {"ok": True, "path": str(path), "audio_stats": data}

    def visual_state(self) -> dict[str, Any]:
        return self._visual_state_from_dir(self.visual_dir)

    def fast_demo_visual_state(self) -> dict[str, Any]:
        return self._visual_state_from_dir(self.fast_demo_visual_dir)

    def _visual_state_from_dir(self, visual_dir: Path) -> dict[str, Any]:
        path = visual_dir / "latest_state.json"
        data, error = _load_json_file(path)
        info = _file_info(path)
        if data is None:
            return {
                "ok": False,
                "reason": error or "not_found",
                "freshness": "unavailable",
                "age_ms": info["age_ms"],
                "state": {},
                "files": {
                    "latest_image": _file_info(visual_dir / "latest_annotated.jpg"),
                    "trigger_image": _file_info(visual_dir / "vlm_trigger.jpg"),
                },
            }
        age_ms = info["age_ms"]
        freshness = "live" if age_ms is not None and age_ms <= 3000 else "stale"
        return {
            "ok": True,
            "reason": None,
            "freshness": freshness,
            "age_ms": age_ms,
            "state": data,
            "files": {
                "latest_image": _file_info(visual_dir / "latest_annotated.jpg"),
                "trigger_image": _file_info(visual_dir / "vlm_trigger.jpg"),
            },
        }

    def openclaw_dashboard(self) -> dict[str, Any]:
        path = self.openclaw_dashboard_path
        data, error = _load_json_file(path)
        info = _file_info(path)
        if data is None:
            return {
                "ok": False,
                "path": str(path),
                "reason": error or "not_found",
                "age_ms": info["age_ms"],
                "dashboard": {},
            }
        if data.get("schema") != OPENCLAW_DASHBOARD_SCHEMA:
            return {
                "ok": False,
                "path": str(path),
                "reason": "unsupported_schema",
                "age_ms": info["age_ms"],
                "dashboard": data,
            }
        updated_age_ms = _timestamp_age_ms(data.get("updated_at"))
        return {
            "ok": True,
            "path": str(path),
            "reason": None,
            "age_ms": updated_age_ms if updated_age_ms is not None else info["age_ms"],
            "dashboard": data,
        }

    def openclaw_status(self) -> dict[str, Any]:
        parsed = urlparse(self.openclaw_url)
        host = parsed.hostname
        port = parsed.port
        if not host or not port:
            return {"ok": False, "url": self.openclaw_url, "reason": "invalid_url"}
        started = time.time()
        try:
            with socket.create_connection((host, port), timeout=0.25):
                pass
        except OSError as exc:
            return {
                "ok": False,
                "url": self.openclaw_url,
                "reason": str(exc),
                "latency_ms": int((time.time() - started) * 1000),
            }
        return {
            "ok": True,
            "url": self.openclaw_url,
            "latency_ms": int((time.time() - started) * 1000),
        }

    def link_process_states(self) -> dict[str, Any]:
        return {
            link: self.link_process_state(link)
            for link in (*STANDARD_LINKS, *FAST_DEMO_LINKS)
        }

    def voice_prewarm_command(self) -> list[str]:
        return [
            sys.executable,
            "-m",
            "base_station.monitor.voice_runtime",
            "--prewarm-asr",
            "--asr-backend",
            self._env_text("XIAOAN_PREWARM_ASR_BACKEND", "sensevoice"),
            "--asr-model-path",
            self._env_text("XIAOAN_PREWARM_ASR_MODEL_PATH", "base_station/models/sensevoice-small"),
            "--asr-device",
            self._env_text("XIAOAN_PREWARM_ASR_DEVICE", "cpu"),
            "--asr-language",
            self._env_text("XIAOAN_PREWARM_ASR_LANGUAGE", "zh"),
            "--audio-output-dir",
            str(self.runtime_dir / "voice_runtime_audio"),
        ]

    def start_voice_prewarm(self) -> dict[str, Any]:
        if self.voice_prewarm_process is not None and self.voice_prewarm_process.poll() is None:
            return {"ok": True, "already_running": True, "state": self.voice_prewarm_state()}
        command = self.voice_prewarm_command()
        self.process_log_dir.mkdir(parents=True, exist_ok=True)
        log_path = self.process_log_dir / "voice_prewarm.log"
        with log_path.open("ab") as log_file:
            log_file.write(f"\n[{_now_iso()}] START {' '.join(command)}\n".encode("utf-8"))
            process = subprocess.Popen(
                command,
                cwd=_repo_root(),
                env=dict(os.environ),
                stdout=log_file,
                stderr=subprocess.STDOUT,
                stdin=subprocess.DEVNULL,
                start_new_session=True,
                close_fds=True,
            )
        self.voice_prewarm_process = process
        self.voice_prewarm_started_at = _now_iso()
        return {"ok": True, "state": self.voice_prewarm_state()}

    def voice_prewarm_state(self) -> dict[str, Any]:
        log_path = self.process_log_dir / "voice_prewarm.log"
        process = self.voice_prewarm_process
        if process is None:
            return {
                "managed": False,
                "running": False,
                "status": "disabled",
                "pid": None,
                "returncode": None,
                "started_at": None,
                "log_path": str(log_path),
            }
        returncode = process.poll()
        return {
            "managed": True,
            "running": returncode is None,
            "status": "running" if returncode is None else "exited",
            "pid": process.pid,
            "returncode": returncode,
            "started_at": self.voice_prewarm_started_at,
            "log_path": str(log_path),
        }

    def fast_demo_tts_prewarm_command(self) -> list[str]:
        return [
            sys.executable,
            "tools/ops/prepare_fast_demo_tts.py",
            "--runtime-dir",
            str(self.runtime_dir),
            "--manifest-path",
            str(self.runtime_dir / "integration_console" / "fast_demo" / "tts_manifest.json"),
        ]

    def start_fast_demo_tts_prewarm(self) -> dict[str, Any]:
        if self.fast_demo_tts_prewarm_process is not None and self.fast_demo_tts_prewarm_process.poll() is None:
            return {"ok": True, "already_running": True, "state": self.fast_demo_tts_prewarm_state()}
        command = self.fast_demo_tts_prewarm_command()
        self.process_log_dir.mkdir(parents=True, exist_ok=True)
        log_path = self.process_log_dir / "fast_demo_tts_prewarm.log"
        with log_path.open("ab") as log_file:
            log_file.write(f"\n[{_now_iso()}] START {' '.join(command)}\n".encode("utf-8"))
            process = subprocess.Popen(
                command,
                cwd=_repo_root(),
                env=dict(os.environ),
                stdout=log_file,
                stderr=subprocess.STDOUT,
                stdin=subprocess.DEVNULL,
                start_new_session=True,
                close_fds=True,
            )
        self.fast_demo_tts_prewarm_process = process
        self.fast_demo_tts_prewarm_started_at = _now_iso()
        return {"ok": True, "state": self.fast_demo_tts_prewarm_state()}

    def fast_demo_tts_prewarm_state(self) -> dict[str, Any]:
        log_path = self.process_log_dir / "fast_demo_tts_prewarm.log"
        manifest_path = self.runtime_dir / "integration_console" / "fast_demo" / "tts_manifest.json"
        process = self.fast_demo_tts_prewarm_process
        manifest, manifest_error = _load_json_file(manifest_path)
        if process is None:
            return {
                "managed": False,
                "running": False,
                "status": "disabled",
                "pid": None,
                "returncode": None,
                "started_at": None,
                "log_path": str(log_path),
                "manifest_path": str(manifest_path),
                "manifest": manifest,
                "manifest_error": manifest_error,
            }
        returncode = process.poll()
        return {
            "managed": True,
            "running": returncode is None,
            "status": "running" if returncode is None else "exited",
            "pid": process.pid,
            "returncode": returncode,
            "started_at": self.fast_demo_tts_prewarm_started_at,
            "log_path": str(log_path),
            "manifest_path": str(manifest_path),
            "manifest": manifest,
            "manifest_error": manifest_error,
        }

    def link_process_state(self, link: str) -> dict[str, Any]:
        process = self.link_processes.get(link)
        log_path = self.process_log_dir / f"{link}.log"
        if process is None:
            return {
                "managed": False,
                "running": False,
                "status": "stopped",
                "pid": None,
                "returncode": None,
                "log_path": str(log_path),
            }
        returncode = process.poll()
        return {
            "managed": True,
            "running": returncode is None,
            "status": "running" if returncode is None else "exited",
            "pid": process.pid,
            "returncode": returncode,
            "log_path": str(log_path),
        }

    def start_fast2_visual_prewarm(self) -> dict[str, Any]:
        """Start Fast2 visual/VLM runtime without enabling robot output."""

        return self.start_fast_demo({
            "link": "fast2",
            "send_to_robot": False,
            "allow_motion": False,
        })

    def fast2_visual_prewarm_state(self) -> dict[str, Any]:
        state = self.link_process_state("fast2")
        return {
            "managed": "fast2" in self.link_processes,
            "running": bool(state.get("running")),
            "status": state.get("status"),
            "pid": state.get("pid"),
            "returncode": state.get("returncode"),
            "log_path": str(self.process_log_dir / "fast2.log"),
            "send_to_robot": bool(self.fast_demo_options.get("fast2", {}).get("send_to_robot", False)),
            "allow_motion": bool(self.fast_demo_options.get("fast2", {}).get("allow_motion", False)),
        }

    def _ws_host_port(self) -> tuple[str, int]:
        parsed = urlparse(self.ws_url)
        host = parsed.hostname or "127.0.0.1"
        if host == "0.0.0.0":
            host = "127.0.0.1"
        return host, int(parsed.port or 8765)

    @staticmethod
    def _env_text(name: str, default: str) -> str:
        value = os.environ.get(name)
        return value.strip() if isinstance(value, str) and value.strip() else default

    @staticmethod
    def _env_truthy(name: str, default: bool = False) -> bool:
        value = os.environ.get(name)
        if value is None:
            return default
        return value.strip().lower() in {"1", "true", "yes", "on"}

    @staticmethod
    def _first_env_text(*names: str) -> str:
        for name in names:
            value = os.environ.get(name)
            if isinstance(value, str) and value.strip():
                return value.strip()
        return ""

    def link_command(self, link: str) -> list[str]:
        if link in {"link1", "link3"}:
            duration = self._env_text(f"XIAOAN_{link.upper()}_MIC_WINDOW", "6.0")
            command = [
                sys.executable,
                "-m",
                "base_station.monitor.voice_runtime",
                "--source",
                "local_mic",
                "--gateway-url",
                self.ws_url,
                "--session-id",
                f"integration-console-{link}",
                "--duration",
                duration,
                "--asr-language",
                self._env_text(f"XIAOAN_{link.upper()}_ASR_LANGUAGE", "zh"),
                "--latest-output",
                str(self.link_voice_output_path(link)),
                "--once",
                *(["--local-demo-reminders-path", str(self.fast_demo_reminders_path)] if link == "link1" else []),
                *(["--disable-companion-fast-path"] if link == "link1" else []),
                "--verbose",
            ]
            mic_device = self._first_env_text(
                f"XIAOAN_{link.upper()}_MIC_DEVICE",
                "XIAOAN_MIC_DEVICE",
            )
            if mic_device:
                command.extend(["--device", mic_device])
            return command
        if link == "link2":
            host, port = self._ws_host_port()
            command = [
                sys.executable,
                "-m",
                "base_station.monitor.emotion_runtime",
                "--source",
                "ws_video_observer",
                "--host",
                host,
                "--port",
                str(port),
                "--count",
                "None",
                "--enable-vlm-gate",
                "--model-backend",
                self._env_text("XIAOAN_LINK2_MODEL_BACKEND", "openface_ov"),
                "--vlm-backend",
                self._env_text("XIAOAN_LINK2_VLM_BACKEND", "openvino_qwen_vl"),
                "--vlm-model-path",
                self._env_text("XIAOAN_LINK2_VLM_MODEL_PATH", DEFAULT_QWEN_VL_MODEL_PATH),
                "--visual-trace-dir",
                str(self.visual_dir),
                "--visual-trace-fps",
                self._env_text("XIAOAN_LINK2_VISUAL_TRACE_FPS", "1.0"),
                "--vlm-max-new-tokens",
                self._env_text("XIAOAN_LINK2_VLM_MAX_NEW_TOKENS", "128"),
                "--device",
                self._env_text("XIAOAN_LINK2_OPENFACE_DEVICE", self._env_text("XIAOAN_LINK2_DEVICE", "NPU")),
                "--vlm-device",
                self._env_text("XIAOAN_LINK2_VLM_DEVICE", "GPU"),
                "--preload-vlm",
                "--verbose",
            ]
            if self._env_truthy("XIAOAN_LINK2_FORCE_VLM", False):
                command.append("--force-vlm")
            return command
        raise ValueError(f"unsupported_link:{link}")

    def fast_demo_command(self, link: str, body: dict[str, Any] | None = None) -> list[str]:
        body = body or {}
        if link in {"fast1", "fast3"}:
            normal_link = "link1" if link == "fast1" else "link3"
            duration = (
                self._env_text(f"XIAOAN_{link.upper()}_MIC_WINDOW", "")
                or self._env_text("XIAOAN_FAST_DEMO_MIC_WINDOW", "")
                or self._env_text(f"XIAOAN_{normal_link.upper()}_MIC_WINDOW", "6.0")
            )
            command = [
                sys.executable,
                "-m",
                "base_station.monitor.voice_runtime",
                "--source",
                "local_mic",
                "--gateway-url",
                self.ws_url,
                "--session-id",
                f"integration-console-{link}",
                "--duration",
                duration,
                "--asr-language",
                self._env_text(f"XIAOAN_{normal_link.upper()}_ASR_LANGUAGE", "zh"),
                "--latest-output",
                str(self.link_voice_output_path(link)),
                "--once",
                "--decision-mode",
                "local_demo",
                "--local-demo-link",
                link,
                "--local-demo-reminders-path",
                str(self.fast_demo_reminders_path),
                "--verbose",
            ]
            if bool(body.get("send_to_robot", False)):
                command.append("--local-demo-send-to-robot")
            if bool(body.get("allow_motion", False)):
                command.append("--local-demo-allow-motion")
            mic_device = self._first_env_text(
                f"XIAOAN_{link.upper()}_MIC_DEVICE",
                "XIAOAN_FAST_DEMO_MIC_DEVICE",
                f"XIAOAN_{normal_link.upper()}_MIC_DEVICE",
                "XIAOAN_MIC_DEVICE",
            )
            if mic_device:
                command.extend(["--device", mic_device])
            return command
        if link == "fast2":
            host, port = self._ws_host_port()
            command = [
                sys.executable,
                "-m",
                "base_station.monitor.emotion_runtime",
                "--source",
                "ws_video_observer",
                "--host",
                host,
                "--port",
                str(port),
                "--count",
                "None",
                "--enable-vlm-gate",
                "--model-backend",
                self._env_text("XIAOAN_LINK2_MODEL_BACKEND", "openface_ov"),
                "--vlm-backend",
                self._env_text("XIAOAN_LINK2_VLM_BACKEND", "openvino_qwen_vl"),
                "--vlm-model-path",
                self._env_text("XIAOAN_LINK2_VLM_MODEL_PATH", DEFAULT_QWEN_VL_MODEL_PATH),
                "--visual-trace-dir",
                str(self.fast_demo_visual_dir),
                "--visual-trace-fps",
                self._env_text("XIAOAN_LINK2_VISUAL_TRACE_FPS", "5.0"),
                "--vlm-min-interval-seconds",
                self._env_text("XIAOAN_LINK2_VLM_MIN_INTERVAL_SECONDS", "8.0"),
                "--vlm-max-new-tokens",
                self._env_text("XIAOAN_LINK2_VLM_MAX_NEW_TOKENS", "128"),
                "--device",
                self._env_text("XIAOAN_FAST2_OPENFACE_DEVICE", self._env_text("XIAOAN_LINK2_OPENFACE_DEVICE", self._env_text("XIAOAN_LINK2_DEVICE", "NPU"))),
                "--vlm-device",
                self._env_text("XIAOAN_FAST2_VLM_DEVICE", self._env_text("XIAOAN_LINK2_VLM_DEVICE", "GPU")),
                "--preload-vlm",
                "--no-agent",
                "--verbose",
            ]
            if self._env_truthy("XIAOAN_FAST2_FORCE_VLM", False):
                command.append("--force-vlm")
            return command
        raise ValueError(f"unsupported_fast_demo_link:{link}")

    def fast_demo_story_voice_command(self) -> list[str]:
        duration = self._env_text("XIAOAN_STORY_MIC_WINDOW", self._env_text("XIAOAN_FAST_DEMO_MIC_WINDOW", "6.0"))
        command = [
            sys.executable,
            "-m",
            "base_station.monitor.voice_runtime",
            "--source",
            "local_mic",
            "--gateway-url",
            self.ws_url,
            "--session-id",
            "integration-console-story",
            "--duration",
            duration,
            "--asr-language",
            self._env_text("XIAOAN_LINK3_ASR_LANGUAGE", "zh"),
            "--latest-output",
            str(self.fast_demo_story_voice_path),
            "--once",
            "--decision-mode",
            "asr_only",
            "--verbose",
        ]
        mic_device = self._first_env_text(
            "XIAOAN_STORY_MIC_DEVICE",
            "XIAOAN_FAST3_MIC_DEVICE",
            "XIAOAN_FAST_DEMO_MIC_DEVICE",
            "XIAOAN_LINK3_MIC_DEVICE",
            "XIAOAN_MIC_DEVICE",
        )
        if mic_device:
            command.extend(["--device", mic_device])
        return command

    def fast_demo_dance_voice_command(self) -> list[str]:
        duration = self._env_text("XIAOAN_DANCE_MIC_WINDOW", self._env_text("XIAOAN_FAST_DEMO_MIC_WINDOW", "6.0"))
        command = [
            sys.executable,
            "-m",
            "base_station.monitor.voice_runtime",
            "--source",
            "local_mic",
            "--gateway-url",
            self.ws_url,
            "--session-id",
            "integration-console-dance",
            "--duration",
            duration,
            "--asr-language",
            self._env_text("XIAOAN_LINK3_ASR_LANGUAGE", "zh"),
            "--latest-output",
            str(self.fast_demo_dance_voice_path),
            "--once",
            "--decision-mode",
            "asr_only",
            "--verbose",
        ]
        mic_device = self._first_env_text(
            "XIAOAN_DANCE_MIC_DEVICE",
            "XIAOAN_FAST3_MIC_DEVICE",
            "XIAOAN_FAST_DEMO_MIC_DEVICE",
            "XIAOAN_LINK3_MIC_DEVICE",
            "XIAOAN_MIC_DEVICE",
        )
        if mic_device:
            command.extend(["--device", mic_device])
        return command

    def link_environment(self, link: str) -> dict[str, str]:
        env = dict(os.environ)
        if link in {"link1", "link2", "link3"}:
            env.setdefault("XIAO_AN_OPENCLAW_BACKEND", "gateway")
            env.setdefault("XIAO_AN_OPENCLAW_GATEWAY_URL", self.openclaw_url)
            env.setdefault("XIAO_AN_OPENCLAW_AGENT", "xiaoan-runtime")
        return env

    def fast_demo_environment(self) -> dict[str, str]:
        env = dict(os.environ)
        for key in (
            "XIAO_AN_OPENCLAW_BACKEND",
            "XIAO_AN_OPENCLAW_GATEWAY_URL",
            "XIAO_AN_OPENCLAW_AGENT",
            "XIAO_AN_OPENCLAW_FRESH_WORK_CAPTURE_SESSION",
        ):
            env.pop(key, None)
        return env

    def start_link(self, body: dict[str, Any]) -> dict[str, Any]:
        link = str(body.get("link") or "").strip()
        try:
            command = self.link_command(link)
        except ValueError as exc:
            return {"ok": False, "error": str(exc)}
        state = self.link_process_state(link)
        if state["running"]:
            return {"ok": True, "link": link, "state": state, "already_running": True}

        self.process_log_dir.mkdir(parents=True, exist_ok=True)
        log_path = self.process_log_dir / f"{link}.log"
        with log_path.open("ab") as log_file:
            log_file.write(f"\n[{_now_iso()}] START {' '.join(command)}\n".encode("utf-8"))
            process = subprocess.Popen(
                command,
                cwd=_repo_root(),
                env=self.link_environment(link),
                stdout=log_file,
                stderr=subprocess.STDOUT,
                stdin=subprocess.DEVNULL,
                start_new_session=True,
                close_fds=True,
            )
        self.link_processes[link] = process
        request_id = uuid.uuid4().hex[:12]
        self.log_event(
            event_type="link.start",
            request_id=request_id,
            action=link,
            payload_summary={"link": link},
            raw_response_summary={"pid": process.pid, "command": command, "log_path": str(log_path)},
        )
        time.sleep(0.1)
        return {
            "ok": True,
            "link": link,
            "request_id": request_id,
            "state": self.link_process_state(link),
            "command_preview": " ".join(command),
        }

    def stop_link(self, body: dict[str, Any]) -> dict[str, Any]:
        link = str(body.get("link") or "").strip()
        if link not in {"link1", "link2", "link3"}:
            return {"ok": False, "error": f"unsupported_link:{link}"}
        process = self.link_processes.get(link)
        if process is None:
            return {"ok": True, "link": link, "state": self.link_process_state(link), "already_stopped": True}
        if process.poll() is None:
            try:
                os.killpg(process.pid, signal.SIGTERM)
            except ProcessLookupError:
                pass
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                os.killpg(process.pid, signal.SIGKILL)
                process.wait(timeout=5)
        self.link_processes.pop(link, None)
        request_id = uuid.uuid4().hex[:12]
        self.log_event(
            event_type="link.stop",
            request_id=request_id,
            action=link,
            payload_summary={"link": link},
            raw_response_summary={"pid": process.pid, "returncode": process.returncode},
        )
        return {
            "ok": True,
            "link": link,
            "request_id": request_id,
                "state": self.link_process_state(link),
        }

    def start_fast_demo(self, body: dict[str, Any]) -> dict[str, Any]:
        link = str(body.get("link") or "").strip()
        try:
            command = self.fast_demo_command(link, body)
        except ValueError as exc:
            return {"ok": False, "error": str(exc)}
        self.fast_demo_options[link] = {
            "send_to_robot": bool(body.get("send_to_robot", False)),
            "allow_motion": bool(body.get("allow_motion", False)),
        }
        state = self.link_process_state(link)
        if state["running"]:
            return {"ok": True, "link": link, "state": state, "already_running": True}

        self.process_log_dir.mkdir(parents=True, exist_ok=True)
        log_path = self.process_log_dir / f"{link}.log"
        with log_path.open("ab") as log_file:
            log_file.write(f"\n[{_now_iso()}] START {' '.join(command)}\n".encode("utf-8"))
            process = subprocess.Popen(
                command,
                cwd=_repo_root(),
                env=self.fast_demo_environment(),
                stdout=log_file,
                stderr=subprocess.STDOUT,
                stdin=subprocess.DEVNULL,
                start_new_session=True,
                close_fds=True,
            )
        self.link_processes[link] = process
        request_id = uuid.uuid4().hex[:12]
        self.log_event(
            event_type="fast_demo.start",
            request_id=request_id,
            action=link,
            payload_summary={
                "link": link,
                "send_to_robot": bool(body.get("send_to_robot", False)),
                "allow_motion": bool(body.get("allow_motion", False)),
            },
            raw_response_summary={"pid": process.pid, "command": command, "log_path": str(log_path)},
        )
        time.sleep(0.1)
        return {
            "ok": True,
            "link": link,
            "request_id": request_id,
            "state": self.link_process_state(link),
            "command_preview": " ".join(command),
        }

    def stop_fast_demo(self, body: dict[str, Any]) -> dict[str, Any]:
        link = str(body.get("link") or "").strip()
        if link not in FAST_DEMO_LINKS:
            return {"ok": False, "error": f"unsupported_fast_demo_link:{link}"}
        process = self.link_processes.get(link)
        if process is None:
            return {"ok": True, "link": link, "state": self.link_process_state(link), "already_stopped": True}
        if process.poll() is None:
            try:
                os.killpg(process.pid, signal.SIGTERM)
            except ProcessLookupError:
                pass
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                os.killpg(process.pid, signal.SIGKILL)
                process.wait(timeout=5)
        self.link_processes.pop(link, None)
        request_id = uuid.uuid4().hex[:12]
        self.log_event(
            event_type="fast_demo.stop",
            request_id=request_id,
            action=link,
            payload_summary={"link": link},
            raw_response_summary={"pid": process.pid, "returncode": process.returncode},
        )
        return {
            "ok": True,
            "link": link,
            "request_id": request_id,
            "state": self.link_process_state(link),
        }

    def execute_fast_demo_plan(self, body: dict[str, Any]) -> dict[str, Any]:
        link = str(body.get("link") or "").strip()
        if link != "fast2":
            return {"ok": False, "error": f"unsupported_fast_demo_execute_link:{link}"}
        visual = self.fast_demo_visual_state()
        if not visual.get("ok"):
            return {"ok": False, "error": visual.get("reason") or "visual_state_unavailable"}
        decision = decide_visual(visual.get("state") if isinstance(visual.get("state"), dict) else {})
        plan = decision.get("robot_plan") if isinstance(decision.get("robot_plan"), dict) else {}
        send_to_robot = bool(body.get("send_to_robot", False))
        allow_motion = bool(body.get("allow_motion", False))
        request_id = uuid.uuid4().hex[:12]
        steps: list[dict[str, Any]] = []
        if not send_to_robot:
            for step in (plan.get("steps") if isinstance(plan.get("steps"), list) else []):
                if isinstance(step, dict):
                    steps.append({"name": step.get("kind"), "ok": True, "skipped": True, "reason": "send_to_robot_disabled"})
            return {
                "ok": True,
                "link": link,
                "request_id": request_id,
                "decision": self._public_fast_demo_decision(decision),
                "steps": steps,
            }
        for step in (plan.get("steps") if isinstance(plan.get("steps"), list) else []):
            if not isinstance(step, dict):
                continue
            kind = str(step.get("kind") or "")
            started = time.time()
            if kind == "expression":
                result = self.send_expression({
                    "expression": step.get("expression"),
                    "duration_ms": step.get("duration_ms"),
                    "loop": step.get("loop", False),
                })
            elif kind == "motion":
                if not allow_motion:
                    steps.append({
                        "name": f"motion:{step.get('action')}",
                        "ok": True,
                        "skipped": True,
                        "reason": "motion_disabled",
                    })
                    continue
                action_id = f"fast-demo-{uuid.uuid4().hex[:8]}"
                result = self.send_motion({
                    "action": step.get("action"),
                    "action_id": action_id,
                    "params": step.get("params") if isinstance(step.get("params"), dict) else {},
                    "timeout_ms": step.get("timeout_ms"),
                    "bench": False,
                })
                steps.append({
                    "name": kind,
                    "ok": bool(result.get("ok")),
                    "duration_ms": int((time.time() - started) * 1000),
                    "result": result,
                })
                if result.get("ok") and step.get("action") != "stop":
                    self._wait_motion_completed(
                        steps,
                        action_id,
                        timeout_ms=int(step.get("timeout_ms") or 1200) + 600,
                    )
                    time.sleep(POST_MOTION_TTS_SETTLE_SECONDS)
                continue
            elif kind == "tts":
                result = self.send_tts({
                    "text": step.get("text"),
                    "duration_ms": step.get("duration_ms"),
                })
            elif kind == "local_sound":
                result = self.send_local_sound({"sound": step.get("sound"), "volume": step.get("volume", 0.8)})
            else:
                result = {"ok": False, "error": f"unsupported_fast_demo_step:{kind}"}
            steps.append({
                "name": kind,
                "ok": bool(result.get("ok")),
                "duration_ms": int((time.time() - started) * 1000),
                "result": result,
            })
        ok = all(step.get("ok") for step in steps)
        self.log_event(
            event_type="fast_demo.execute",
            request_id=request_id,
            action=link,
            payload_summary={"link": link, "send_to_robot": send_to_robot, "allow_motion": allow_motion},
            result="ok" if ok else "failed",
            raw_response_summary={"decision": self._public_fast_demo_decision(decision), "steps": steps},
        )
        return {
            "ok": ok,
            "link": link,
            "request_id": request_id,
            "decision": self._public_fast_demo_decision(decision),
            "steps": steps,
        }

    def state(self) -> dict[str, Any]:
        ws_state = read_ws_state(self.runtime_dir)
        visual_state = self.visual_state()
        dashboard_state = self.openclaw_dashboard()
        process_states = self.link_process_states()
        raw_state = ws_state.get("state") if isinstance(ws_state.get("state"), dict) else {}
        devices = raw_state.get("devices") if isinstance(raw_state.get("devices"), dict) else {}
        sessions = raw_state.get("sessions") if isinstance(raw_state.get("sessions"), dict) else {}
        selected_device_id = raw_state.get("selected_device_id")
        if not selected_device_id and sessions:
            selected_device_id = next(iter(sessions.keys()))
        selected_device = devices.get(selected_device_id, {}) if selected_device_id else {}
        selected_session = sessions.get(selected_device_id, {}) if selected_device_id else {}
        last_heartbeat = selected_device.get("last_heartbeat") or {}
        heartbeat_ts = _parse_received_at(last_heartbeat)
        heartbeat_age_ms = int(max(0.0, time.time() - heartbeat_ts) * 1000) if heartbeat_ts else None
        robot_online = bool(selected_device_id and heartbeat_age_ms is not None and heartbeat_age_ms <= 30000)
        latest_image = _file_info(self.runtime_dir / "latest.jpg")
        latest_audio = _file_info(self.runtime_dir / "latest_audio.pcm")
        audio_stats, audio_stats_error = _load_json_file(self.runtime_dir / "audio_stats.json")
        demo1, _ = _load_json_file(self.runtime_dir / "demo1_transcript.json")
        assistant, _ = _load_json_file(self.runtime_dir / "assistant_capture_result.json")
        link_voice = {
            link: self.link_voice_state(link)
            for link in ("link1", "link3")
        }
        status_payload = {}
        if isinstance(selected_device.get("last_status"), dict):
            status_payload = selected_device["last_status"].get("payload") or {}
        heartbeat_payload = last_heartbeat.get("payload") if isinstance(last_heartbeat, dict) else {}
        hello_payload = (selected_device.get("last_hello") or {}).get("payload") if isinstance(selected_device, dict) else {}
        merged_robot = {}
        for source in (hello_payload, heartbeat_payload, status_payload, selected_session):
            if isinstance(source, dict):
                merged_robot.update(source)

        robot = {
            "online": robot_online,
            "selected_device_id": selected_device_id,
            "last_hello": selected_device.get("last_hello"),
            "last_heartbeat": last_heartbeat or None,
            "last_heartbeat_age_ms": heartbeat_age_ms,
            "last_status": selected_device.get("last_status"),
            "battery": merged_robot.get("battery"),
            "charging": merged_robot.get("charging"),
            "dock": merged_robot.get("dock") or merged_robot.get("docked"),
            "wifi_rssi": merged_robot.get("wifi_rssi"),
            "free_heap": merged_robot.get("free_heap"),
            "reset_reason": merged_robot.get("reset_reason"),
            "last_command_ack": raw_state.get("last_command_ack"),
            "last_motion_completed": raw_state.get("last_motion_completed"),
            "last_audio_playback_done": raw_state.get("last_audio_playback_done"),
            "last_error": raw_state.get("last_error"),
        }
        tts_runtime = raw_state.get("tts_runtime") if isinstance(raw_state.get("tts_runtime"), dict) else {}
        reminder_result = self.process_due_fast_demo_reminders()
        media = {
            "latest_image": latest_image,
            "latest_audio": latest_audio,
            "audio_stats": audio_stats,
            "audio_stats_error": audio_stats_error,
        }
        asr = {
            "demo1_transcript": demo1,
            "assistant_capture_result": assistant,
        }
        links = self.link_state(
            media=media,
            asr=asr,
            robot=robot,
            visual=visual_state,
            dashboard=dashboard_state,
            processes=process_states,
            link_voice=link_voice,
        )
        fast_demo = self.fast_demo_state(robot=robot, processes=process_states)

        return {
            "ok": True,
            "current_time": _now_iso(),
            "console": self.health(),
            "ws_server": ws_state,
            "robot": robot,
            "tts_runtime": tts_runtime,
            "media": media,
            "asr": asr,
            "link_voice": link_voice,
            "openclaw": self.openclaw_status(),
            "openclaw_dashboard": dashboard_state,
            "visual": visual_state,
            "links": links,
            "fast_demo": fast_demo,
            "fast_demo_reminders": self.fast_demo_reminders_state(last_result=reminder_result),
            "fast_demo_story": self.fast_demo_story_state(),
            "processes": process_states,
            "tools": self.tool_catalog(),
            "recent_events": self.recent_events(limit=STATE_EVENT_LIMIT),
        }

    def link_state(
        self,
        *,
        media: dict[str, Any],
        asr: dict[str, Any],
        robot: dict[str, Any],
        visual: dict[str, Any],
        dashboard: dict[str, Any],
        processes: dict[str, Any] | None = None,
        link_voice: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        latest_image = media.get("latest_image") if isinstance(media.get("latest_image"), dict) else {}
        latest_audio = media.get("latest_audio") if isinstance(media.get("latest_audio"), dict) else {}
        audio_stats = media.get("audio_stats") if isinstance(media.get("audio_stats"), dict) else {}
        demo1 = asr.get("demo1_transcript") if isinstance(asr.get("demo1_transcript"), dict) else {}
        assistant = asr.get("assistant_capture_result") if isinstance(asr.get("assistant_capture_result"), dict) else {}
        processes = processes or {}
        link_voice = link_voice or {}
        link1_voice = link_voice.get("link1") if isinstance(link_voice.get("link1"), dict) else {}
        link3_voice = link_voice.get("link3") if isinstance(link_voice.get("link3"), dict) else {}
        dashboard_payload = dashboard.get("dashboard") if isinstance(dashboard.get("dashboard"), dict) else {}
        latest_reply = dashboard_payload.get("latest_reply") if isinstance(dashboard_payload.get("latest_reply"), dict) else {}
        dashboard_age = dashboard.get("age_ms")
        dashboard_fresh = bool(
            dashboard.get("ok")
            and dashboard_age is not None
            and int(dashboard_age) <= 30000
        )
        execution = assistant.get("execution_result") if isinstance(assistant.get("execution_result"), dict) else {}
        if not execution and isinstance(assistant.get("openclaw_result"), dict):
            execution = assistant["openclaw_result"].get("execution_result") or {}

        link1_output = self._display_voice_output(
            link1_voice.get("output") if isinstance(link1_voice.get("output"), dict) else {}
        )
        link3_output = self._display_voice_output(
            link3_voice.get("output") if isinstance(link3_voice.get("output"), dict) else {}
        )
        link1_phase = self._voice_phase(
            link1_voice.get("output") if isinstance(link1_voice.get("output"), dict) else {},
            processes.get("link1") if isinstance(processes.get("link1"), dict) else {},
        )
        link3_phase = self._voice_phase(
            link3_voice.get("output") if isinstance(link3_voice.get("output"), dict) else {},
            processes.get("link3") if isinstance(processes.get("link3"), dict) else {},
        )
        link1_asr_text = self._voice_text(link1_output) or str(demo1.get("transcript") or "").strip()
        link3_asr_text = self._voice_text(link3_output)
        link1_openclaw_text = self._voice_reply_text(link1_output)
        link3_openclaw_text = self._voice_reply_text(link3_output)
        openclaw_text = (
            link1_openclaw_text
            or str(
                assistant.get("reply_text")
                or assistant.get("display_text")
                or assistant.get("spoken_text")
                or latest_reply.get("display_text")
                or dashboard_payload.get("status_text")
                or ""
            ).strip()
        )
        dashboard_text = ""
        if dashboard_fresh:
            dashboard_text = str(
                latest_reply.get("display_text")
                or dashboard_payload.get("status_text")
                or ""
            ).strip()
        spoken_text = str(
            link3_output.get("spoken_text")
            or latest_reply.get("spoken_text")
            or assistant.get("spoken_text")
            or ""
        ).strip()
        robot_ack = robot.get("last_command_ack")
        robot_motion = robot.get("last_motion_completed")
        robot_audio = robot.get("last_audio_playback_done")
        robot_execution_ok = self._recent_robot_execution_ok(robot)
        link1_running = bool((processes.get("link1") or {}).get("running"))
        link2_running = bool((processes.get("link2") or {}).get("running"))
        link3_running = bool((processes.get("link3") or {}).get("running"))
        link1_completed_once = bool(
            (processes.get("link1") or {}).get("status") == "exited"
            and (processes.get("link1") or {}).get("returncode") == 0
            and link1_voice.get("ok")
        )
        link3_completed_once = bool(
            (processes.get("link3") or {}).get("status") == "exited"
            and (processes.get("link3") or {}).get("returncode") == 0
            and link3_voice.get("ok")
        )
        link1_voice_age = link1_voice.get("age_ms")
        link3_voice_age = link3_voice.get("age_ms")
        link1_voice_fresh = bool(
            link1_voice.get("ok")
            and link1_voice_age is not None
            and int(link1_voice_age) <= 30000
        )
        link3_voice_fresh = bool(
            link3_voice.get("ok")
            and link3_voice_age is not None
            and int(link3_voice_age) <= 30000
        )
        link1_audio = self._voice_audio_info(link1_output)
        link3_audio = self._voice_audio_info(link3_output)
        link1_audio_fresh = link1_voice_fresh or _fresh(link1_audio, 30000)
        link3_audio_fresh = link3_voice_fresh or _fresh(link3_audio, 30000)
        camera_fresh = _fresh(latest_image, FRESH_IMAGE_MS)
        visual_fresh = bool(visual.get("ok") and visual.get("age_ms") is not None and int(visual.get("age_ms") or 0) <= FRESH_VISUAL_MS)
        executed_actions = execution.get("executed_actions") if isinstance(execution.get("executed_actions"), list) else []
        link2_care_voice = self.link2_openclaw_care_voice_state()

        link1_steps = [
            _step("voice runtime", link1_running or link1_completed_once, (processes.get("link1") or {}).get("pid")),
            _step("麦克风", link1_audio_fresh, link1_audio.get("updated_at") or link1_voice.get("updated_at")),
            _step("ASR 文本", bool(link1_asr_text), link1_asr_text),
            _step("OpenClaw 回复", bool(link1_openclaw_text), link1_openclaw_text),
            _step("基站屏幕更新", bool(dashboard_text), dashboard_text),
            _step("机器人执行提醒", robot_execution_ok, self._robot_execution_summary(robot)),
        ]
        link2_steps = [
            _step("emotion runtime", link2_running, (processes.get("link2") or {}).get("pid")),
            _step("相机连接", camera_fresh, latest_image.get("updated_at")),
            _step("ws_video 分析快照", visual_fresh, visual.get("freshness")),
            _step("视觉状态文件", bool(visual.get("ok")), visual.get("reason")),
            _step("OpenClaw 关怀语音", bool(link2_care_voice.get("text")), link2_care_voice.get("text") or link2_care_voice.get("reason")),
        ]
        link3_steps = [
            _step("voice runtime", link3_running or link3_completed_once, (processes.get("link3") or {}).get("pid")),
            _step("麦克风", link3_audio_fresh, link3_audio.get("updated_at") or link3_voice.get("updated_at")),
            _step("ASR 文本", bool(link3_asr_text), link3_asr_text),
            _step("秒级机器人动作/语音", robot_execution_ok or bool(executed_actions), self._robot_execution_summary(robot)),
            _step("OpenClaw 后续关怀语音", bool(spoken_text or link3_openclaw_text), spoken_text or link3_openclaw_text),
        ]

        return {
            "camera": {
                "status": "live" if camera_fresh else ("stale" if latest_image.get("exists") else "missing"),
                "done": camera_fresh,
                "latest_image": latest_image,
            },
            "link1": {
                "status": self._status_from_steps(link1_steps) if (link1_running or link1_completed_once) else "idle",
                "done": all(step["ok"] for step in link1_steps),
                "steps": link1_steps,
                "asr_text": link1_asr_text,
                "openclaw_text": link1_openclaw_text,
                "dashboard_text": dashboard_text,
                "robot_execution": self._robot_execution_summary(robot),
                "voice": link1_voice,
                "voice_phase": link1_phase,
            },
            "link2": {
                "status": self._status_from_steps(link2_steps) if link2_running else "idle",
                "done": all(step["ok"] for step in link2_steps),
                "steps": link2_steps,
                "visual_freshness": visual.get("freshness"),
                "openclaw_care_voice": link2_care_voice,
            },
            "link3": {
                "status": self._status_from_steps(link3_steps) if (link3_running or link3_completed_once) else "idle",
                "done": all(step["ok"] for step in link3_steps),
                "steps": link3_steps,
                "asr_text": link3_asr_text,
                "fast_response": self._robot_execution_summary(robot),
                "follow_up_text": spoken_text or link3_openclaw_text,
                "voice": link3_voice,
                "voice_phase": link3_phase,
            },
        }

    def fast_demo_state(
        self,
        *,
        robot: dict[str, Any],
        processes: dict[str, Any],
    ) -> dict[str, Any]:
        voice = {
            link: self.link_voice_state(link)
            for link in ("fast1", "fast3")
        }
        fast_visual = self.fast_demo_visual_state()
        fast1 = self._fast_demo_voice_link_state("fast1", voice.get("fast1") or {}, processes, robot)
        fast3 = self._fast_demo_voice_link_state("fast3", voice.get("fast3") or {}, processes, robot)
        fast2 = self._fast_demo_visual_link_state(fast_visual, processes)
        return {
            "public_label": "智能大脑回复",
            "voice": voice,
            "visual": fast_visual,
            "fast1": fast1,
            "fast2": fast2,
            "fast3": fast3,
            "dance": self.fast_demo_dance_state(robot=robot),
        }

    def fast_demo_story_state(self) -> dict[str, Any]:
        data = self._load_fast_demo_story()
        summary = story_state_summary(data)
        summary["path"] = str(self.fast_demo_story_path)
        voice, voice_error = _load_json_file(self.fast_demo_story_voice_path)
        summary["voice"] = voice if isinstance(voice, dict) else {}
        summary["voice_error"] = voice_error
        return summary

    def fast_demo_dance_state(self, *, robot: dict[str, Any] | None = None) -> dict[str, Any]:
        voice, voice_error = _load_json_file(self.fast_demo_dance_voice_path)
        voice = voice if isinstance(voice, dict) else {}
        output = self._display_voice_output(voice)
        transcript = self._voice_text(output)
        matched = self._dance_keyword_matched(transcript)
        execution = voice.get("robot_execution") if isinstance(voice.get("robot_execution"), dict) else {}
        audio = self._voice_audio_info(output)
        info = _file_info(self.fast_demo_dance_voice_path)
        robot_summary = self._robot_execution_summary(robot or {})
        steps = [
            _step("麦克风", bool(transcript) or voice.get("event_type") == "dance.voice_recording", audio.get("audio_path") or voice.get("reason")),
            _step("ASR 文本", bool(transcript), transcript),
            _step("关键词：跳舞", matched, "matched" if matched else "waiting"),
            _step("唱歌跳舞命令", bool(execution.get("ok")) or bool(execution.get("skipped")), execution or robot_summary),
        ]
        active = voice.get("event_type") == "dance.voice_recording"
        return {
            "ok": bool(voice),
            "status": "recording" if active else (self._status_from_steps(steps) if voice else "idle"),
            "done": bool(voice) and all(step["ok"] for step in steps),
            "path": str(self.fast_demo_dance_voice_path),
            "age_ms": info.get("age_ms"),
            "updated_at": info.get("updated_at"),
            "voice_error": voice_error,
            "voice": voice,
            "voice_phase": self._voice_phase(output, {"running": active} if active else {}),
            "asr_text": transcript,
            "keyword_matched": matched,
            "robot_execution": execution or robot_summary,
            "steps": steps,
        }

    @staticmethod
    def _dance_keyword_matched(transcript: str) -> bool:
        text = str(transcript or "").strip()
        return any(keyword in text for keyword in DANCE_KEYWORDS)

    def listen_fast_demo_dance(self, body: dict[str, Any]) -> dict[str, Any]:
        request_id = uuid.uuid4().hex[:12]
        started = time.time()
        voice = self._capture_dance_voice(body)
        transcript = self._voice_text(self._display_voice_output(voice))
        matched = self._dance_keyword_matched(transcript)
        send_to_robot = bool(body.get("send_to_robot", False))
        allow_motion = bool(body.get("allow_motion", False))
        if not matched:
            execution = {
                "ok": False,
                "skipped": True,
                "reason": "dance_keyword_not_matched",
                "expected_keywords": list(DANCE_KEYWORDS),
            }
        elif not send_to_robot:
            execution = {"ok": True, "skipped": True, "reason": "send_to_robot_disabled"}
        elif not allow_motion:
            execution = {"ok": True, "skipped": True, "reason": "allow_motion_disabled"}
        else:
            execution = self.send_dance_demo_sequence({
                "device_id": body.get("device_id"),
                "style": "ode_to_joy",
                "duration_ms": body.get("duration_ms", 13000),
            })

        output = dict(voice)
        output.update({
            "event_type": voice.get("event_type") or "dance.voice_result",
            "handled": matched,
            "reason": "dance_keyword_matched" if matched else "dance_keyword_not_matched",
            "text": transcript,
            "dance_keyword_matched": matched,
            "robot_execution": execution,
            "updated_at": _now_iso(),
        })
        _atomic_write_json(self.fast_demo_dance_voice_path, output)
        result = {
            "ok": bool(matched and execution.get("ok")),
            "request_id": request_id,
            "transcript": transcript,
            "keyword_matched": matched,
            "send_to_robot": send_to_robot,
            "allow_motion": allow_motion,
            "voice": output,
            "execution": execution,
            "duration_ms": int((time.time() - started) * 1000),
        }
        self.log_event(
            event_type="fast_demo.dance.listen",
            request_id=request_id,
            action="dance.listen",
            payload_summary={
                "transcript": transcript,
                "keyword_matched": matched,
                "send_to_robot": send_to_robot,
                "allow_motion": allow_motion,
            },
            result="ok" if result["ok"] else "skipped",
            raw_response_summary=result,
        )
        return result

    def start_fast_demo_story(self, body: dict[str, Any]) -> dict[str, Any]:
        send_to_robot = bool(body.get("send_to_robot", False))
        allow_motion = bool(body.get("allow_motion", False))
        with self.fast_demo_story_lock:
            state = build_story_state()
            _atomic_write_json(self.fast_demo_story_path, state)

        node = get_story_node(state.get("current_node"))
        execution = self._execute_story_node(
            node.as_dict(),
            send_to_robot=send_to_robot,
            allow_motion=allow_motion,
            move_out_first=True,
        )
        state["last_execution"] = execution
        state["send_to_robot"] = send_to_robot
        state["allow_motion"] = allow_motion
        state["updated_at"] = _now_iso()
        with self.fast_demo_story_lock:
            _atomic_write_json(self.fast_demo_story_path, state)

        request_id = uuid.uuid4().hex[:12]
        result = {
            "ok": bool(execution.get("ok", True)),
            "request_id": request_id,
            "story": story_state_summary(state),
            "execution": execution,
        }
        self.log_event(
            event_type="fast_demo.story.start",
            request_id=request_id,
            action="story.start",
            payload_summary={"send_to_robot": send_to_robot, "allow_motion": allow_motion},
            result="ok" if result["ok"] else "failed",
            raw_response_summary=result,
        )
        return result

    def choose_fast_demo_story(self, body: dict[str, Any]) -> dict[str, Any]:
        choice_text = str(body.get("choice") or body.get("choice_id") or "").strip()
        send_to_robot = bool(body.get("send_to_robot", False))
        allow_motion = bool(body.get("allow_motion", False))
        with self.fast_demo_story_lock:
            state = self._load_fast_demo_story()
            if not state.get("active"):
                return {
                    "ok": False,
                    "error": "story_not_active",
                    "story": story_state_summary(state),
                }
            choice = resolve_story_choice(state, choice_text)
            if choice is None:
                node = get_story_node(state.get("current_node"))
                return {
                    "ok": False,
                    "error": "choice_not_matched",
                    "choice": choice_text,
                    "available_choices": [item.as_dict() for item in node.choices],
                    "story": story_state_summary(state),
                }
            state = advance_story_state(state, choice)
            _atomic_write_json(self.fast_demo_story_path, state)

        node = get_story_node(state.get("current_node"))
        execution = self._execute_story_node(node.as_dict(), send_to_robot=send_to_robot, allow_motion=allow_motion)
        state["last_execution"] = execution
        state["send_to_robot"] = send_to_robot
        state["allow_motion"] = allow_motion
        state["updated_at"] = _now_iso()
        with self.fast_demo_story_lock:
            _atomic_write_json(self.fast_demo_story_path, state)

        request_id = uuid.uuid4().hex[:12]
        result = {
            "ok": bool(execution.get("ok", True)),
            "request_id": request_id,
            "choice": choice.as_dict(),
            "story": story_state_summary(state),
            "execution": execution,
        }
        self.log_event(
            event_type="fast_demo.story.choose",
            request_id=request_id,
            action="story.choose",
            payload_summary={"choice": choice_text, "send_to_robot": send_to_robot, "allow_motion": allow_motion},
            result="ok" if result["ok"] else "failed",
            raw_response_summary=result,
        )
        return result

    def listen_fast_demo_story(self, body: dict[str, Any]) -> dict[str, Any]:
        request_id = uuid.uuid4().hex[:12]
        started = time.time()
        voice = self._capture_story_voice(body)
        transcript = self._voice_text(self._display_voice_output(voice))
        send_to_robot = bool(body.get("send_to_robot", False))
        allow_motion = bool(body.get("allow_motion", False))
        state = self._load_fast_demo_story()
        action_result: dict[str, Any]
        action = "story.listen"

        if is_story_start_request(transcript):
            action_result = self.start_fast_demo_story({
                "send_to_robot": send_to_robot,
                "allow_motion": allow_motion,
            })
            action = "story.voice_start"
        elif state.get("active"):
            action_result = self.choose_fast_demo_story({
                "choice": transcript,
                "send_to_robot": send_to_robot,
                "allow_motion": allow_motion,
            })
            action = "story.voice_choice"
        else:
            action_result = {
                "ok": False,
                "error": "story_keyword_not_matched",
                "transcript": transcript,
                "expected_keywords": ["故事", "讲故事", "开始故事"],
                "story": story_state_summary(state),
            }

        result = {
            "ok": bool(action_result.get("ok")),
            "request_id": request_id,
            "transcript": transcript,
            "voice": voice,
            "action": action,
            "error": action_result.get("error"),
            "result": action_result,
            "duration_ms": int((time.time() - started) * 1000),
        }
        self.log_event(
            event_type="fast_demo.story.listen",
            request_id=request_id,
            action=action,
            payload_summary={"transcript": transcript, "send_to_robot": send_to_robot, "allow_motion": allow_motion},
            result="ok" if result["ok"] else "failed",
            raw_response_summary=result,
        )
        return result

    def stop_fast_demo_story(self, body: dict[str, Any] | None = None) -> dict[str, Any]:
        with self.fast_demo_story_lock:
            state = stop_story_state(self._load_fast_demo_story())
            _atomic_write_json(self.fast_demo_story_path, state)
        request_id = uuid.uuid4().hex[:12]
        result = {"ok": True, "request_id": request_id, "story": story_state_summary(state)}
        self.log_event(
            event_type="fast_demo.story.stop",
            request_id=request_id,
            action="story.stop",
            payload_summary={},
            result="ok",
            raw_response_summary=result,
        )
        return result

    def _execute_story_node(
        self,
        node: dict[str, Any],
        *,
        send_to_robot: bool,
        allow_motion: bool = False,
        move_out_first: bool = False,
    ) -> dict[str, Any]:
        if not send_to_robot:
            return {
                "ok": True,
                "skipped": True,
                "reason": "send_to_robot_disabled",
                "node_id": node.get("id"),
                "steps": [
                    {"name": "motion", "ok": True, "skipped": True},
                    {"name": "expression", "ok": True, "skipped": True},
                    {"name": "tts", "ok": True, "skipped": True},
                ],
            }

        steps: list[dict[str, Any]] = []
        story_steps: list[dict[str, Any]] = []
        if move_out_first:
            story_steps.append({
                "name": "motion",
                "action": "move_out_of_dock",
                "params": {"speed": 0.5, "distance_cm": 8.0},
                "timeout_ms": 1400,
            })
        story_steps.extend((
            {"name": "expression", "expression": node.get("expression"), "duration_ms": 1500},
            {"name": "tts", "text": node.get("text"), "duration_ms": 3000},
        ))
        for step in story_steps:
            started = time.time()
            if step["name"] == "motion":
                if not allow_motion:
                    result = {"ok": True, "skipped": True, "reason": "allow_motion_disabled"}
                else:
                    action_id = f"story-{uuid.uuid4().hex[:8]}"
                    result = self.send_motion({
                        "action": step.get("action"),
                        "action_id": action_id,
                        "params": step.get("params"),
                        "timeout_ms": step.get("timeout_ms"),
                    })
                steps.append({
                    "name": step["name"],
                    "ok": bool(result.get("ok")),
                    "duration_ms": int((time.time() - started) * 1000),
                    "result": result,
                })
                if allow_motion and result.get("ok"):
                    self._wait_motion_completed(
                        steps,
                        action_id,
                        timeout_ms=int(step.get("timeout_ms") or 1400) + 600,
                    )
                    time.sleep(POST_MOTION_TTS_SETTLE_SECONDS)
                continue
            elif step["name"] == "expression":
                result = self.send_expression({
                    "expression": step.get("expression"),
                    "duration_ms": step.get("duration_ms"),
                    "loop": False,
                })
            else:
                ok_to_send, guard = self._story_tts_guard(str(step.get("text") or ""))
                if not ok_to_send:
                    result = guard
                else:
                    result = self.send_tts({
                        "text": step.get("text"),
                        "duration_ms": step.get("duration_ms"),
                        "playback_mode": "buffered",
                    })
            steps.append({
                "name": step["name"],
                "ok": bool(result.get("ok")),
                "duration_ms": int((time.time() - started) * 1000),
                "result": result,
            })
        return {"ok": all(step.get("ok") for step in steps), "node_id": node.get("id"), "steps": steps}

    def _story_tts_guard(self, text: str) -> tuple[bool, dict[str, Any]]:
        manifest_path = self.runtime_dir / "integration_console" / "fast_demo" / "tts_manifest.json"
        manifest, _ = _load_json_file(manifest_path)
        max_bytes = _clamp_int(os.environ.get("XIAOAN_STORY_TTS_MAX_PCM_BYTES"), STORY_TTS_MAX_PCM_BYTES, 32_000, 1_200_000)
        if not isinstance(manifest, dict):
            return True, {"ok": True, "skipped": False, "reason": "manifest_unavailable"}
        for item in manifest.get("items") if isinstance(manifest.get("items"), list) else []:
            if not isinstance(item, dict) or item.get("link") != "story":
                continue
            if str(item.get("text") or "").strip() != text.strip():
                continue
            pcm_bytes = int(item.get("pcm_bytes") or 0)
            if pcm_bytes <= max_bytes:
                return True, {"ok": True, "pcm_bytes": pcm_bytes, "max_pcm_bytes": max_bytes}
            return False, {
                "ok": False,
                "error": "story_tts_pcm_too_large",
                "pcm_bytes": pcm_bytes,
                "max_pcm_bytes": max_bytes,
                "duration_ms": item.get("duration_ms"),
            }
        return True, {"ok": True, "skipped": False, "reason": "story_manifest_item_not_found"}

    def _capture_story_voice(self, body: dict[str, Any]) -> dict[str, Any]:
        transcript = str(body.get("transcript") or "").strip()
        if transcript:
            output = {
                "text": transcript,
                "event_type": "asr.transcript",
                "handled": False,
                "reason": "provided_transcript",
            }
            _atomic_write_json(self.fast_demo_story_voice_path, output)
            return output

        command = self.fast_demo_story_voice_command()
        self.process_log_dir.mkdir(parents=True, exist_ok=True)
        self.fast_demo_story_voice_path.parent.mkdir(parents=True, exist_ok=True)
        log_path = self.process_log_dir / "story_voice.log"
        _atomic_write_json(
            self.fast_demo_story_voice_path,
            {
                "event_type": "story.voice_recording",
                "handled": False,
                "reason": "recording",
                "text": "",
                "updated_at": _now_iso(),
                "duration_ms": int(float(command[command.index("--duration") + 1]) * 1000)
                if "--duration" in command
                else None,
                "command_preview": " ".join(command),
                "log_path": str(log_path),
            },
        )
        with log_path.open("ab") as log_file:
            log_file.write(f"\n[{_now_iso()}] START {' '.join(command)}\n".encode("utf-8"))
            try:
                completed = subprocess.run(
                    command,
                    cwd=_repo_root(),
                    env=self.fast_demo_environment(),
                    stdout=log_file,
                    stderr=subprocess.STDOUT,
                    stdin=subprocess.DEVNULL,
                    timeout=_clamp_float(os.environ.get("XIAOAN_STORY_VOICE_TIMEOUT"), 90.0, 10.0, 180.0),
                    check=False,
                )
            except subprocess.TimeoutExpired as exc:
                output = {
                    "event_type": "story.voice_timeout",
                    "handled": False,
                    "reason": "voice_runtime_timeout",
                    "text": "",
                    "command_preview": " ".join(command),
                    "timeout": exc.timeout,
                    "log_path": str(log_path),
                }
                _atomic_write_json(self.fast_demo_story_voice_path, output)
                return output

        output, error = _load_json_file(self.fast_demo_story_voice_path)
        if isinstance(output, dict):
            output.setdefault("returncode", completed.returncode)
            output.setdefault("log_path", str(log_path))
            return output
        return {
            "event_type": "story.voice_error",
            "handled": False,
            "reason": error or "missing_latest_output",
            "text": "",
            "returncode": completed.returncode,
            "command_preview": " ".join(command),
            "log_path": str(log_path),
        }

    def _capture_dance_voice(self, body: dict[str, Any]) -> dict[str, Any]:
        transcript = str(body.get("transcript") or "").strip()
        if transcript:
            output = {
                "text": transcript,
                "event_type": "asr.transcript",
                "handled": False,
                "reason": "provided_transcript",
                "updated_at": _now_iso(),
            }
            _atomic_write_json(self.fast_demo_dance_voice_path, output)
            return output

        command = self.fast_demo_dance_voice_command()
        self.process_log_dir.mkdir(parents=True, exist_ok=True)
        self.fast_demo_dance_voice_path.parent.mkdir(parents=True, exist_ok=True)
        log_path = self.process_log_dir / "dance_voice.log"
        _atomic_write_json(
            self.fast_demo_dance_voice_path,
            {
                "event_type": "dance.voice_recording",
                "handled": False,
                "reason": "recording",
                "text": "",
                "updated_at": _now_iso(),
                "duration_ms": int(float(command[command.index("--duration") + 1]) * 1000)
                if "--duration" in command
                else None,
                "command_preview": " ".join(command),
                "log_path": str(log_path),
            },
        )
        with log_path.open("ab") as log_file:
            log_file.write(f"\n[{_now_iso()}] START {' '.join(command)}\n".encode("utf-8"))
            try:
                completed = subprocess.run(
                    command,
                    cwd=_repo_root(),
                    env=self.fast_demo_environment(),
                    stdout=log_file,
                    stderr=subprocess.STDOUT,
                    stdin=subprocess.DEVNULL,
                    timeout=_clamp_float(os.environ.get("XIAOAN_DANCE_VOICE_TIMEOUT"), 90.0, 10.0, 180.0),
                    check=False,
                )
            except subprocess.TimeoutExpired as exc:
                output = {
                    "event_type": "dance.voice_timeout",
                    "handled": False,
                    "reason": "voice_runtime_timeout",
                    "text": "",
                    "command_preview": " ".join(command),
                    "timeout": exc.timeout,
                    "log_path": str(log_path),
                    "updated_at": _now_iso(),
                }
                _atomic_write_json(self.fast_demo_dance_voice_path, output)
                return output

        output, error = _load_json_file(self.fast_demo_dance_voice_path)
        if isinstance(output, dict):
            output.setdefault("returncode", completed.returncode)
            output.setdefault("log_path", str(log_path))
            return output
        return {
            "event_type": "dance.voice_error",
            "handled": False,
            "reason": error or "missing_latest_output",
            "text": "",
            "returncode": completed.returncode,
            "command_preview": " ".join(command),
            "log_path": str(log_path),
            "updated_at": _now_iso(),
        }

    def _load_fast_demo_story(self) -> dict[str, Any]:
        data, _ = _load_json_file(self.fast_demo_story_path)
        if not isinstance(data, dict) or data.get("schema_version") != STORY_SCHEMA_VERSION:
            return stop_story_state({})
        return data

    def fast_demo_reminders_state(self, *, last_result: dict[str, Any] | None = None) -> dict[str, Any]:
        payload = self._load_fast_demo_reminders()
        items = payload.get("items") if isinstance(payload.get("items"), list) else []
        pending = [item for item in items if isinstance(item, dict) and item.get("status") == "pending"]
        fired = [item for item in items if isinstance(item, dict) and item.get("status") == "fired"]
        return {
            "ok": True,
            "path": str(self.fast_demo_reminders_path),
            "count": len(items),
            "pending_count": len(pending),
            "fired_count": len(fired),
            "next_due_at": min((str(item.get("due_at")) for item in pending if item.get("due_at")), default=None),
            "items": items[-10:],
            "last_result": last_result or {},
        }

    def process_due_fast_demo_reminders(self) -> dict[str, Any]:
        with self.fast_demo_reminder_lock:
            payload = self._load_fast_demo_reminders()
            items = payload.get("items") if isinstance(payload.get("items"), list) else []
            if not items:
                return {"ok": True, "processed": 0, "due": 0}
            now_ts = time.time()
            due_indexes: list[int] = []
            for index, item in enumerate(items):
                if not isinstance(item, dict) or item.get("status") != "pending":
                    continue
                due_ts = _iso_timestamp(item.get("due_at"))
                if due_ts is None or due_ts > now_ts:
                    continue
                due_indexes.append(index)
                item["status"] = "firing"
                item["firing_at"] = _now_iso()
            if not due_indexes:
                return {"ok": True, "processed": 0, "due": 0}
            payload["updated_at"] = _now_iso()
            payload["items"] = items
            _atomic_write_json(self.fast_demo_reminders_path, payload)

        processed = 0
        results: list[dict[str, Any]] = []
        for index in due_indexes:
            item = items[index]
            decision = build_reminder_due_decision(item)
            execution = self._execute_fast_demo_decision_plan(
                decision,
                send_to_robot=bool(item.get("send_to_robot", False)),
                allow_motion=bool(item.get("allow_motion", False)),
            )
            item["status"] = "fired" if execution.get("ok") else "failed"
            item["fired_at"] = _now_iso()
            item["fire_decision"] = self._public_fast_demo_decision(decision)
            item["fire_execution"] = execution
            results.append({"id": item.get("id"), "ok": execution.get("ok"), "execution": execution})
            processed += 1

        with self.fast_demo_reminder_lock:
            latest_payload = self._load_fast_demo_reminders()
            latest_items = latest_payload.get("items") if isinstance(latest_payload.get("items"), list) else []
            by_id = {
                str(item.get("id")): item
                for item in latest_items
                if isinstance(item, dict) and item.get("id") is not None
            }
            for item in items:
                item_id = str(item.get("id") or "")
                if item_id and item_id in by_id:
                    by_id[item_id].update(item)
            latest_payload["updated_at"] = _now_iso()
            latest_payload["items"] = latest_items
            _atomic_write_json(self.fast_demo_reminders_path, latest_payload)
        return {"ok": True, "processed": processed, "due": len(due_indexes), "results": results}

    def _load_fast_demo_reminders(self) -> dict[str, Any]:
        data, _ = _load_json_file(self.fast_demo_reminders_path)
        if data is None:
            return {
                "schema_version": "xiaoan.fast_demo_reminders.v1",
                "updated_at": None,
                "items": [],
            }
        if not isinstance(data.get("items"), list):
            data["items"] = []
        return data

    def _execute_fast_demo_decision_plan(
        self,
        decision: dict[str, Any],
        *,
        send_to_robot: bool,
        allow_motion: bool,
    ) -> dict[str, Any]:
        plan = decision.get("robot_plan") if isinstance(decision.get("robot_plan"), dict) else {}
        steps: list[dict[str, Any]] = []
        if not send_to_robot:
            for step in (plan.get("steps") if isinstance(plan.get("steps"), list) else []):
                if isinstance(step, dict):
                    steps.append({"name": step.get("kind"), "ok": True, "skipped": True, "reason": "send_to_robot_disabled"})
            return {"ok": True, "steps": steps}
        for step in (plan.get("steps") if isinstance(plan.get("steps"), list) else []):
            if not isinstance(step, dict):
                continue
            kind = str(step.get("kind") or "")
            started = time.time()
            if kind == "expression":
                result = self.send_expression({
                    "expression": step.get("expression"),
                    "duration_ms": step.get("duration_ms"),
                    "loop": step.get("loop", False),
                })
            elif kind == "motion":
                if not allow_motion:
                    steps.append({
                        "name": f"motion:{step.get('action')}",
                        "ok": True,
                        "skipped": True,
                        "reason": "motion_disabled",
                    })
                    continue
                action_id = f"fast-demo-{uuid.uuid4().hex[:8]}"
                result = self.send_motion({
                    "action": step.get("action"),
                    "action_id": action_id,
                    "params": step.get("params") if isinstance(step.get("params"), dict) else {},
                    "timeout_ms": step.get("timeout_ms"),
                    "bench": False,
                })
                steps.append({
                    "name": kind,
                    "ok": bool(result.get("ok")),
                    "duration_ms": int((time.time() - started) * 1000),
                    "result": result,
                })
                if result.get("ok") and step.get("action") != "stop":
                    self._wait_motion_completed(
                        steps,
                        action_id,
                        timeout_ms=int(step.get("timeout_ms") or 1200) + 600,
                    )
                continue
            elif kind == "tts":
                result = self.send_tts({"text": step.get("text"), "duration_ms": step.get("duration_ms")})
            elif kind == "local_sound":
                result = self.send_local_sound({"sound": step.get("sound"), "volume": step.get("volume", 0.8)})
            else:
                result = {"ok": False, "error": f"unsupported_fast_demo_step:{kind}"}
            steps.append({
                "name": kind,
                "ok": bool(result.get("ok")),
                "duration_ms": int((time.time() - started) * 1000),
                "result": result,
            })
        return {"ok": all(step.get("ok") for step in steps), "steps": steps}

    def _maybe_start_fast2_auto_care(
        self,
        decision: dict[str, Any],
        visual: dict[str, Any],
        *,
        running: bool,
    ) -> dict[str, Any]:
        if not running or decision.get("intent") != "visual_care":
            return self.fast2_auto_care_last_result or {"ok": True, "status": "idle"}
        options = self.fast_demo_options.get("fast2", {})
        if not bool(options.get("send_to_robot", False)):
            return {
                "ok": True,
                "status": "disabled",
                "reason": "send_to_robot_disabled",
                "last_result": self.fast2_auto_care_last_result,
            }
        key = self._fast2_auto_care_key(decision, visual)
        now = time.monotonic()
        with self.fast2_auto_care_lock:
            if self.fast2_auto_care_running:
                return {
                    "ok": True,
                    "status": "running",
                    "trigger_key": self.fast2_auto_care_last_key,
                    "last_result": self.fast2_auto_care_last_result,
                }
            if key == self.fast2_auto_care_last_key:
                return {
                    "ok": True,
                    "status": "already_handled",
                    "trigger_key": key,
                    "last_result": self.fast2_auto_care_last_result,
                }
            if now - self.fast2_auto_care_last_started_monotonic < FAST2_AUTO_CARE_COOLDOWN_SECONDS:
                return {
                    "ok": True,
                    "status": "cooldown",
                    "trigger_key": key,
                    "cooldown_seconds": FAST2_AUTO_CARE_COOLDOWN_SECONDS,
                    "last_result": self.fast2_auto_care_last_result,
                }
            self.fast2_auto_care_running = True
            self.fast2_auto_care_last_key = key
            self.fast2_auto_care_last_started_monotonic = now

        frozen_decision = json.loads(json.dumps(decision, ensure_ascii=False))
        frozen_options = {
            "send_to_robot": bool(options.get("send_to_robot", False)),
            "allow_motion": bool(options.get("allow_motion", False)),
        }
        thread = threading.Thread(
            target=self._run_fast2_auto_care,
            args=(frozen_decision, frozen_options, key),
            name="fast2-auto-care",
            daemon=True,
        )
        thread.start()
        return {
            "ok": True,
            "status": "started",
            "trigger_key": key,
            "send_to_robot": frozen_options["send_to_robot"],
            "allow_motion": frozen_options["allow_motion"],
            "last_result": self.fast2_auto_care_last_result,
        }

    def _run_fast2_auto_care(
        self,
        decision: dict[str, Any],
        options: dict[str, bool],
        trigger_key: str,
    ) -> None:
        request_id = uuid.uuid4().hex[:12]
        try:
            execution = self._execute_fast_demo_decision_plan(
                decision,
                send_to_robot=bool(options.get("send_to_robot", False)),
                allow_motion=bool(options.get("allow_motion", False)),
            )
            result = {
                "ok": bool(execution.get("ok")),
                "status": "done" if execution.get("ok") else "failed",
                "link": "fast2",
                "request_id": request_id,
                "trigger_key": trigger_key,
                "send_to_robot": bool(options.get("send_to_robot", False)),
                "allow_motion": bool(options.get("allow_motion", False)),
                "decision": self._public_fast_demo_decision(decision),
                "steps": execution.get("steps", []),
            }
            self.log_event(
                event_type="fast_demo.auto_care",
                request_id=request_id,
                action="fast2",
                payload_summary={
                    "trigger_key": trigger_key,
                    "send_to_robot": result["send_to_robot"],
                    "allow_motion": result["allow_motion"],
                },
                result="ok" if result["ok"] else "failed",
                raw_response_summary=result,
            )
        except Exception as exc:  # pragma: no cover - defensive background guard
            result = {
                "ok": False,
                "status": "error",
                "link": "fast2",
                "request_id": request_id,
                "trigger_key": trigger_key,
                "error": str(exc),
            }
            self.log_event(
                event_type="fast_demo.auto_care",
                request_id=request_id,
                action="fast2",
                payload_summary={"trigger_key": trigger_key},
                result="error",
                raw_response_summary=result,
            )
        with self.fast2_auto_care_lock:
            self.fast2_auto_care_last_result = result
            self.fast2_auto_care_running = False

    @staticmethod
    def _fast2_auto_care_key(decision: dict[str, Any], visual: dict[str, Any]) -> str:
        trace = visual.get("state") if isinstance(visual.get("state"), dict) else {}
        files = visual.get("files") if isinstance(visual.get("files"), dict) else {}
        latest_image = files.get("latest_image") if isinstance(files.get("latest_image"), dict) else {}
        vlm = trace.get("vlm") if isinstance(trace.get("vlm"), dict) else {}
        trigger = decision.get("trigger") if isinstance(decision.get("trigger"), dict) else {}
        parts = [
            str(vlm.get("request_id") or ""),
            str(vlm.get("trigger_frame_id") or ""),
            str(trace.get("frame_id") or ""),
            str(latest_image.get("mtime") or ""),
            json.dumps(trigger, ensure_ascii=False, sort_keys=True),
        ]
        digest = uuid.uuid5(uuid.NAMESPACE_URL, "|".join(parts)).hex[:12]
        return f"fast2-care-{digest}"

    def _fast_demo_voice_link_state(
        self,
        link: str,
        voice_state: dict[str, Any],
        processes: dict[str, Any],
        robot: dict[str, Any],
    ) -> dict[str, Any]:
        process = processes.get(link) if isinstance(processes.get(link), dict) else {}
        output = self._display_voice_output(
            voice_state.get("output") if isinstance(voice_state.get("output"), dict) else {}
        )
        phase = self._voice_phase(output, process)
        asr_text = self._voice_text(output)
        decision = output.get("fast_demo_decision") if isinstance(output.get("fast_demo_decision"), dict) else {}
        if asr_text and not decision:
            try:
                decision = decide_voice(link, asr_text)
            except ValueError:
                decision = {}
        brain_text = self._voice_reply_text(output) or str(decision.get("reply_text") or "").strip()
        audio = self._voice_audio_info(output)
        voice_fresh = bool(
            voice_state.get("ok")
            and voice_state.get("age_ms") is not None
            and int(voice_state.get("age_ms") or 0) <= 30000
        )
        audio_fresh = voice_fresh or _fresh(audio, 30000)
        running = bool(process.get("running"))
        completed_once = bool(process.get("status") == "exited" and process.get("returncode") == 0 and voice_state.get("ok"))
        robot_plan = decision.get("robot_plan") if isinstance(decision.get("robot_plan"), dict) else {}
        execution = output.get("robot_execution") if isinstance(output.get("robot_execution"), dict) else {}
        steps = [
            _step("voice runtime", running or completed_once, process.get("pid")),
            _step("麦克风", audio_fresh, audio.get("updated_at") or voice_state.get("updated_at")),
            _step("ASR 文本", bool(asr_text), asr_text),
            _step("智能大脑回复", bool(brain_text), brain_text),
            _step("表情/TTS/动作计划", bool(robot_plan.get("steps")), self._fast_demo_plan_summary(robot_plan, execution)),
        ]
        return {
            "status": self._status_from_steps(steps) if (running or completed_once or voice_state.get("ok")) else "idle",
            "done": all(step["ok"] for step in steps),
            "steps": steps,
            "asr_text": asr_text,
            "brain_text": brain_text,
            "decision": self._public_fast_demo_decision(decision),
            "robot_plan": robot_plan,
            "robot_execution": execution or self._robot_execution_summary(robot),
            "voice": voice_state,
            "voice_phase": phase,
        }

    def _fast_demo_visual_link_state(
        self,
        visual: dict[str, Any],
        processes: dict[str, Any],
    ) -> dict[str, Any]:
        process = processes.get("fast2") if isinstance(processes.get("fast2"), dict) else {}
        running = bool(process.get("running"))
        trace = visual.get("state") if isinstance(visual.get("state"), dict) else {}
        files = visual.get("files") if isinstance(visual.get("files"), dict) else {}
        latest_image = files.get("latest_image") if isinstance(files.get("latest_image"), dict) else {}
        visual_fresh = bool(visual.get("ok") and visual.get("age_ms") is not None and int(visual.get("age_ms") or 0) <= FRESH_VISUAL_MS)
        decision = decide_visual(trace) if visual_fresh else {}
        brain_text = str(decision.get("reply_text") or "").strip() if visual_fresh else ""
        robot_plan = decision.get("robot_plan") if isinstance(decision.get("robot_plan"), dict) else {}
        auto_execution = (
            self._maybe_start_fast2_auto_care(decision, visual, running=running)
            if visual_fresh
            else (self.fast2_auto_care_last_result or {"ok": True, "status": "idle"})
        )
        steps = [
            _step("emotion runtime", running, process.get("pid")),
            _step("ws_video 分析快照", _fresh(latest_image, FRESH_VISUAL_MS), visual.get("freshness")),
            _step("视觉模型推理", visual_fresh, self._fast_demo_visual_summary(trace, visual_fresh=visual_fresh)),
            _step("智能大脑回复", bool(brain_text), brain_text),
            _step("表情/TTS/动作计划", bool(robot_plan.get("steps")) and bool(brain_text), self._fast_demo_plan_summary(robot_plan, auto_execution)),
        ]
        return {
            "status": self._status_from_steps(steps) if (running or visual_fresh) else "idle",
            "done": all(step["ok"] for step in steps),
            "steps": steps,
            "visual": visual,
            "brain_text": brain_text,
            "decision": self._public_fast_demo_decision(decision) if visual_fresh else {},
            "robot_plan": robot_plan if visual_fresh else {},
            "robot_execution": auto_execution,
        }

    @staticmethod
    def _public_fast_demo_decision(decision: dict[str, Any]) -> dict[str, Any]:
        if not decision:
            return {}
        return {
            "public_label": decision.get("public_label") or "智能大脑回复",
            "intent": decision.get("intent"),
            "confidence": decision.get("confidence"),
            "reason": decision.get("reason"),
            "reply_text": decision.get("reply_text"),
            "trigger": decision.get("trigger") if isinstance(decision.get("trigger"), dict) else {},
        }

    @staticmethod
    def _fast_demo_plan_summary(plan: dict[str, Any], execution: dict[str, Any]) -> dict[str, Any]:
        steps = plan.get("steps") if isinstance(plan.get("steps"), list) else []
        return {
            "allow_motion_required": bool(plan.get("allow_motion_required")),
            "steps": [
                {
                    "kind": step.get("kind"),
                    "action": step.get("action") or step.get("expression") or step.get("sound") or ("tts" if step.get("kind") == "tts" else None),
                }
                for step in steps
                if isinstance(step, dict)
            ],
            "executed_actions": execution.get("executed_actions") if isinstance(execution.get("executed_actions"), list) else [],
            "skipped_actions": execution.get("skipped_actions") if isinstance(execution.get("skipped_actions"), list) else [],
        }

    @staticmethod
    def _fast_demo_visual_summary(trace: dict[str, Any], *, visual_fresh: bool = True) -> dict[str, Any]:
        observation = trace.get("observation") if isinstance(trace.get("observation"), dict) else {}
        cv = trace.get("cv_sample") if isinstance(trace.get("cv_sample"), dict) else {}
        gate = trace.get("gate") if isinstance(trace.get("gate"), dict) else {}
        gate_result = gate.get("result") if isinstance(gate.get("result"), dict) else {}
        vlm = trace.get("vlm") if isinstance(trace.get("vlm"), dict) else {}
        vlm_result = vlm.get("result") if isinstance(vlm.get("result"), dict) else {}
        vlm_status = vlm.get("status")
        if not visual_fresh and vlm_status == "running":
            vlm_status = "stale_running"
        return {
            "frame_id": trace.get("frame_id"),
            "face_detected": observation.get("face_detected"),
            "emotion_tag": cv.get("emotion_tag"),
            "confidence": cv.get("confidence"),
            "fatigue_score": cv.get("fatigue_score"),
            "gate_should_trigger": gate_result.get("should_trigger"),
            "gate_reason": gate_result.get("reason"),
            "vlm_status": vlm_status,
            "vlm_label": vlm_result.get("expression_label") or vlm_result.get("emotion_tag"),
        }

    def link_voice_state(self, link: str) -> dict[str, Any]:
        path = self.link_voice_output_path(link)
        data, error = _load_json_file(path)
        info = _file_info(path)
        if data is None:
            return {
                "ok": False,
                "reason": error or "not_found",
                "path": str(path),
                "age_ms": info.get("age_ms"),
                "updated_at": info.get("updated_at"),
                "output": {},
            }
        return {
            "ok": True,
            "reason": None,
            "path": str(path),
            "age_ms": info.get("age_ms"),
            "updated_at": info.get("updated_at"),
            "output": data,
        }

    def link2_openclaw_care_voice_state(self) -> dict[str, Any]:
        log_path = Path(self.runtime_dir) / "integration_console" / "process_logs" / "link2.log"
        info = _file_info(log_path)
        if not info.get("exists"):
            return {
                "ok": False,
                "text": "",
                "source": "link2.log",
                "path": str(log_path),
                "reason": "not_found",
                "age_ms": None,
                "updated_at": None,
            }
        try:
            raw = log_path.read_text(encoding="utf-8", errors="replace")
        except OSError as exc:
            return {
                "ok": False,
                "text": "",
                "source": "link2.log",
                "path": str(log_path),
                "reason": str(exc),
                "age_ms": info.get("age_ms"),
                "updated_at": info.get("updated_at"),
            }

        tail = raw[-300_000:]
        name_idx = tail.rfind('"name": "xiaoan.robot.care"')
        if name_idx < 0:
            return {
                "ok": False,
                "text": "",
                "source": "link2.log",
                "path": str(log_path),
                "reason": "no_care_tool_call",
                "age_ms": info.get("age_ms"),
                "updated_at": info.get("updated_at"),
            }

        region = tail[name_idx:]
        arguments = self._extract_json_field_object(region, "arguments")
        text = str(arguments.get("text") or "").strip() if isinstance(arguments, dict) else ""
        context = tail[max(0, name_idx - 8000):name_idx]
        frame_ids = re.findall(r'"frame_id"\s*:\s*(\d+)', context)
        emotions = re.findall(r'"emotion_tag"\s*:\s*"([^"]+)"', context)
        fatigues = re.findall(r'"fatigue_score"\s*:\s*([0-9.]+)', context)
        return {
            "ok": bool(text),
            "text": text,
            "reason": str(arguments.get("reason") or "") if isinstance(arguments, dict) else "bad_arguments",
            "source": "link2.log",
            "path": str(log_path),
            "age_ms": info.get("age_ms"),
            "updated_at": info.get("updated_at"),
            "frame_id": int(frame_ids[-1]) if frame_ids else None,
            "emotion_tag": emotions[-1] if emotions else "",
            "fatigue_score": float(fatigues[-1]) if fatigues else None,
        }

    @staticmethod
    def _extract_json_field_object(text: str, field: str) -> dict[str, Any]:
        field_idx = text.find(f'"{field}"')
        if field_idx < 0:
            return {}
        colon_idx = text.find(":", field_idx)
        start_idx = text.find("{", colon_idx)
        if colon_idx < 0 or start_idx < 0:
            return {}
        depth = 0
        in_string = False
        escape = False
        for idx in range(start_idx, len(text)):
            char = text[idx]
            if in_string:
                if escape:
                    escape = False
                elif char == "\\":
                    escape = True
                elif char == '"':
                    in_string = False
                continue
            if char == '"':
                in_string = True
            elif char == "{":
                depth += 1
            elif char == "}":
                depth -= 1
                if depth == 0:
                    try:
                        data = json.loads(text[start_idx:idx + 1])
                    except json.JSONDecodeError:
                        return {}
                    return data if isinstance(data, dict) else {}
        return {}

    @staticmethod
    def _voice_text(output: dict[str, Any]) -> str:
        return str(output.get("text") or "").strip()

    @staticmethod
    def _display_voice_output(output: dict[str, Any]) -> dict[str, Any]:
        if output.get("event_type") in {"voice.recording", "voice.runtime_started"}:
            previous = output.get("previous_output")
            if isinstance(previous, dict):
                return previous
        return output

    @staticmethod
    def _voice_phase(output: dict[str, Any], process: dict[str, Any]) -> dict[str, Any]:
        event_type = output.get("event_type")
        reason = output.get("reason")
        if event_type in {"voice.recording", "story.voice_recording", "dance.voice_recording"}:
            return {
                "phase": "recording",
                "mic": "on",
                "label": "MIC ON",
                "detail": "正在收音",
            }
        if event_type == "voice.runtime_started":
            return {
                "phase": "starting",
                "mic": "off",
                "label": "MIC OFF",
                "detail": "启动录音 runtime",
            }
        if event_type == "asr.transcript" and reason == "openclaw_pending":
            return {
                "phase": "openclaw_pending",
                "mic": "off",
                "label": "MIC OFF",
                "detail": "ASR 完成，等待 OpenClaw",
            }
        if event_type == "asr.transcript":
            return {
                "phase": "done",
                "mic": "off",
                "label": "MIC OFF",
                "detail": "本轮录音已结束",
            }
        if process.get("running"):
            return {
                "phase": "processing",
                "mic": "off",
                "label": "MIC OFF",
                "detail": "处理中",
            }
        return {
            "phase": "idle",
            "mic": "off",
            "label": "MIC OFF",
            "detail": "空闲",
        }

    @staticmethod
    def _voice_reply_text(output: dict[str, Any]) -> str:
        latest = output.get("latest_reply") if isinstance(output.get("latest_reply"), dict) else {}
        return str(
            output.get("reply_text")
            or output.get("display_text")
            or output.get("spoken_text")
            or latest.get("reply_text")
            or latest.get("display_text")
            or latest.get("spoken_text")
            or ""
        ).strip()

    @staticmethod
    def _voice_audio_info(output: dict[str, Any]) -> dict[str, Any]:
        event = output.get("event") if isinstance(output.get("event"), dict) else {}
        payload = event.get("payload") if isinstance(event.get("payload"), dict) else {}
        audio = payload.get("audio") if isinstance(payload.get("audio"), dict) else {}
        if not audio and isinstance(output.get("audio"), dict):
            audio = output["audio"]
        path = audio.get("audio_path") or audio.get("original_audio_path")
        return _file_info(Path(path)) if path else {"exists": False, "age_ms": None, "updated_at": None}

    @staticmethod
    def _status_from_steps(steps: list[dict[str, Any]]) -> str:
        if all(step.get("ok") for step in steps):
            return "complete"
        if any(step.get("ok") for step in steps):
            return "running"
        return "idle"

    @staticmethod
    def _robot_execution_summary(robot: dict[str, Any]) -> dict[str, Any]:
        return {
            "last_command_ack": robot.get("last_command_ack"),
            "last_motion_completed": robot.get("last_motion_completed"),
            "last_audio_playback_done": robot.get("last_audio_playback_done"),
        }

    @staticmethod
    def _recent_robot_execution_ok(robot: dict[str, Any], max_age_ms: int = 30000) -> bool:
        for key in ("last_command_ack", "last_motion_completed", "last_audio_playback_done"):
            item = robot.get(key)
            timestamp = _parse_received_at(item)
            if timestamp is not None and int(max(0.0, time.time() - timestamp) * 1000) <= max_age_ms:
                return True
        return False

    def log_event(
        self,
        *,
        event_type: str,
        request_id: str,
        action: str,
        payload_summary: Any = None,
        result: str = "ok",
        duration_ms: int = 0,
        error: str | None = None,
        raw_response_summary: Any = None,
    ) -> None:
        item = {
            "timestamp": _now_iso(),
            "event_type": event_type,
            "request_id": request_id,
            "action": action,
            "payload_summary": _sanitize_payload(payload_summary or {}),
            "result": result,
            "duration_ms": duration_ms,
            "error": error,
            "raw_response_summary": _sanitize_payload(raw_response_summary or {}),
        }
        try:
            self.event_dir.mkdir(parents=True, exist_ok=True)
            with self.event_log_path.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(item, ensure_ascii=False, sort_keys=True) + "\n")
        except OSError:
            return

    def recent_events(self, limit: int = EVENT_LIMIT) -> list[dict[str, Any]]:
        try:
            lines = self.event_log_path.read_text(encoding="utf-8").splitlines()
        except OSError:
            return []
        events: list[dict[str, Any]] = []
        for line in lines[-limit:]:
            try:
                item = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(item, dict):
                events.append(item)
        return events

    def export_logs(self) -> dict[str, Any]:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        path = self.event_dir / f"export_{timestamp}.json"
        payload = {
            "exported_at": _now_iso(),
            "state": self.state(),
            "recent_events": self.recent_events(limit=EVENT_LIMIT),
            "runtime_files": {
                "ws_state": _file_info(self.runtime_dir / "ws_state.json"),
                "latest_image": _file_info(self.runtime_dir / "latest.jpg"),
                "latest_audio": _file_info(self.runtime_dir / "latest_audio.pcm"),
                "audio_stats": _file_info(self.runtime_dir / "audio_stats.json"),
                "demo1_transcript": _file_info(self.runtime_dir / "demo1_transcript.json"),
                "assistant_capture_result": _file_info(self.runtime_dir / "assistant_capture_result.json"),
            },
        }
        _atomic_write_json(path, payload)
        request_id = uuid.uuid4().hex[:12]
        self.log_event(
            event_type="logs.export",
            request_id=request_id,
            action="export",
            result="ok",
            raw_response_summary={"path": str(path)},
        )
        return {"ok": True, "path": str(path), "request_id": request_id}

    async def _send_agent_command_async(self, payload: dict[str, Any]) -> dict[str, Any]:
        if self.command_sender is not None:
            return self.command_sender(payload)
        try:
            import websockets
        except ImportError as exc:
            return {"ok": False, "error": f"missing websockets dependency: {exc}"}
        message = {"type": "agent.command", "payload": payload}
        ack_timeout = _agent_ack_timeout_seconds(payload)
        try:
            async with websockets.connect(self.ws_url, open_timeout=3) as websocket:
                await asyncio.wait_for(
                    websocket.send(json.dumps(message, ensure_ascii=False)),
                    timeout=3,
                )
                raw_ack = await asyncio.wait_for(websocket.recv(), timeout=ack_timeout)
        except Exception as exc:
            return {"ok": False, "error": str(exc), "ws_url": self.ws_url}
        try:
            ack = json.loads(raw_ack)
        except json.JSONDecodeError:
            return {"ok": False, "error": "bad_json_ack", "raw": raw_ack[:500]}
        payload = ack.get("payload")
        ok = isinstance(payload, dict) and bool(payload.get("ok"))
        return {"ok": ok, "ack": ack, "error": None if ok else (payload or {}).get("error")}

    def send_agent_command(self, payload: dict[str, Any], *, action: str, event_type: str) -> dict[str, Any]:
        request_id = uuid.uuid4().hex[:12]
        started = time.time()
        result = asyncio.run(self._send_agent_command_async(payload))
        duration_ms = int((time.time() - started) * 1000)
        self.log_event(
            event_type=event_type,
            request_id=request_id,
            action=action,
            payload_summary=payload,
            result="ok" if result.get("ok") else "failed",
            duration_ms=duration_ms,
            error=result.get("error"),
            raw_response_summary=result.get("ack") or result,
        )
        result["request_id"] = request_id
        result["duration_ms"] = duration_ms
        return result

    def send_expression(self, body: dict[str, Any]) -> dict[str, Any]:
        expression = str(body.get("expression") or "idle")
        if expression not in EXPRESSIONS:
            return {"ok": False, "error": f"unsupported_expression:{expression}"}
        payload = {
            "device_id": body.get("device_id"),
            "command": "display.expression",
            "expression": expression,
            "duration_ms": int(body.get("duration_ms") or 1500),
            "loop": bool(body.get("loop", False)),
        }
        return self.send_agent_command(payload, action=f"expression:{expression}", event_type="robot.expression")

    def _safe_motion_payload(self, body: dict[str, Any]) -> tuple[dict[str, Any] | None, str | None]:
        action = str(body.get("action") or "stop")
        if action not in MOTION_ACTIONS:
            return None, f"unsupported_motion:{action}"
        raw_params = body.get("params") if isinstance(body.get("params"), dict) else {}
        bench = bool(body.get("bench", False))
        speed = _clamp_float(raw_params.get("speed"), 1.0, 0.0 if bench else 0.52, 1.0)
        timeout_ms = _clamp_int(raw_params.get("timeout_ms", body.get("timeout_ms")), 1200, 1, 10000 if bench else 1200)
        params: dict[str, Any] = {}
        if action in {"move_out_of_dock", "move_back_to_dock", "turn"}:
            params["speed"] = speed
        if action == "move_out_of_dock":
            params["distance_cm"] = _clamp_float(raw_params.get("distance_cm"), 8.0, 0.0, 100.0 if bench else 10.0)
        if action == "turn":
            params["angle_deg"] = _clamp_float(raw_params.get("angle_deg"), 15.0, -45.0 if not bench else -360.0, 45.0 if not bench else 360.0)
        if raw_params.get("duration_ms") is not None:
            params["duration_ms"] = _clamp_int(raw_params.get("duration_ms"), 500, 1, 10000 if bench else 1200)
        return {
            "device_id": body.get("device_id"),
            "command": "motion.execute",
            "action": action,
            "action_id": body.get("action_id") or f"console-{uuid.uuid4().hex[:8]}",
            "params": params,
            "timeout_ms": timeout_ms,
            "bench": bench,
        }, None

    def send_motion(self, body: dict[str, Any]) -> dict[str, Any]:
        payload, error = self._safe_motion_payload(body)
        if payload is None:
            return {"ok": False, "error": error}
        return self.send_agent_command(payload, action=f"motion:{payload['action']}", event_type="robot.motion")

    def _audio_allowed(self) -> tuple[bool, str | None]:
        elapsed = time.time() - self.last_audio_sent_at
        if elapsed < AUDIO_COOLDOWN_SECONDS:
            return False, f"audio_cooldown:{round(AUDIO_COOLDOWN_SECONDS - elapsed, 2)}s"
        return True, None

    def _wait_audio_cooldown(self) -> None:
        elapsed = time.time() - self.last_audio_sent_at
        if elapsed < AUDIO_COOLDOWN_SECONDS:
            time.sleep(AUDIO_COOLDOWN_SECONDS - elapsed)

    def send_local_sound(self, body: dict[str, Any]) -> dict[str, Any]:
        allowed, reason = self._audio_allowed()
        if not allowed:
            return {"ok": False, "error": reason}
        sound = str(body.get("sound") or "care_01").strip()
        if not sound:
            return {"ok": False, "error": "missing_sound"}
        payload = {
            "device_id": body.get("device_id"),
            "command": "audio.play_local",
            "sound": sound,
            "volume": _clamp_float(body.get("volume"), 0.8, 0.0, 1.0),
        }
        result = self.send_agent_command(payload, action=f"local_sound:{sound}", event_type="robot.local_sound")
        if result.get("ok"):
            self.last_audio_sent_at = time.time()
        return result

    def send_tts(self, body: dict[str, Any]) -> dict[str, Any]:
        allowed, reason = self._audio_allowed()
        if not allowed:
            return {"ok": False, "error": reason}
        text = str(body.get("text") or "").strip()
        if not text:
            return {"ok": False, "error": "missing_text"}
        payload = {
            "device_id": body.get("device_id"),
            "command": "audio.play_tts",
            "text": text[:300],
        }
        playback_mode = body.get("playback_mode")
        if playback_mode in {"buffered", "streaming"}:
            payload["playback_mode"] = playback_mode
        result = self.send_agent_command(payload, action="tts", event_type="robot.tts")
        if result.get("ok"):
            self.last_audio_sent_at = time.time()
        return result

    def send_sing_dance_demo(self, body: dict[str, Any] | None = None) -> dict[str, Any]:
        body = body or {}
        payload = {
            "device_id": body.get("device_id"),
            "command": "demo.sing_dance",
            "style": str(body.get("style") or "ode_to_joy"),
            "duration_ms": _clamp_int(body.get("duration_ms"), 13000, 8000, 15000),
        }
        return self.send_agent_command(payload, action="demo.sing_dance", event_type="robot.demo")

    def send_dance_demo_sequence(self, body: dict[str, Any] | None = None) -> dict[str, Any]:
        body = body or {}
        steps: list[dict[str, Any]] = []
        device_id = body.get("device_id")

        started = time.time()
        expression = self.send_expression({
            "device_id": device_id,
            "expression": "surprised",
            "duration_ms": 1800,
            "loop": False,
        })
        self._append_step(steps, "expression:surprised", started, expression)
        if not expression.get("ok"):
            return {"ok": False, "steps": steps, "failed_step": "expression:surprised"}

        self._wait_audio_cooldown()
        started = time.time()
        intro = self.send_tts({
            "device_id": device_id,
            "text": DANCE_INTRO_TEXT,
            "playback_mode": "buffered",
        })
        self._append_step(steps, "tts:dance_intro", started, intro)
        if not intro.get("ok"):
            return {"ok": False, "steps": steps, "failed_step": "tts:dance_intro"}

        started = time.time()
        dance = self.send_sing_dance_demo({
            "device_id": device_id,
            "style": body.get("style") or "ode_to_joy",
            "duration_ms": body.get("duration_ms", 13000),
        })
        self._append_step(steps, "demo.sing_dance", started, dance)
        return {
            "ok": all(step.get("ok") for step in steps),
            "steps": steps,
            "intro_text": DANCE_INTRO_TEXT,
        }

    def run_scenario(self, body: dict[str, Any]) -> dict[str, Any]:
        scenario = str(body.get("scenario") or "")
        device_id = body.get("device_id")
        request_id = uuid.uuid4().hex[:12]
        started = time.time()
        steps: list[dict[str, Any]] = []
        try:
            if scenario == "direct-smoke":
                self._scenario_expression(steps, device_id, "idle", 500)
                self._scenario_expression(steps, device_id, "happy", 1500)
                self._scenario_sound(steps, device_id, "success_ding")
            elif scenario == "care-loop-safe":
                self._scenario_expression(steps, device_id, "caring", 1500)
                action_id = f"scenario-{uuid.uuid4().hex[:8]}"
                self._scenario_motion(steps, device_id, "move_out_of_dock", action_id=action_id)
                self._wait_motion_completed(steps, action_id, timeout_ms=1600)
                self._scenario_sound(steps, device_id, "care_01")
                self._scenario_expression(steps, device_id, "idle", 500)
            elif scenario == "return-dock":
                self._scenario_motion(steps, device_id, "move_back_to_dock")
                self._scenario_expression(steps, device_id, "idle", 500)
            elif scenario == "stop-all":
                self._scenario_motion(steps, device_id, "stop")
            elif scenario == "camera-check":
                self._scenario_check_file(steps, "latest.jpg", max_age_ms=3000)
            elif scenario == "audio-check":
                self._scenario_check_file(steps, "latest_audio.pcm", max_age_ms=5000)
                self._scenario_audio_stats(steps)
            else:
                raise ValueError(f"unsupported_scenario:{scenario}")
        except Exception as exc:
            ok = False
            error = str(exc)
        else:
            ok = all(step.get("ok") for step in steps)
            error = None if ok else "one_or_more_steps_failed"
        duration_ms = int((time.time() - started) * 1000)
        result = {
            "ok": ok,
            "scenario": scenario,
            "request_id": request_id,
            "duration_ms": duration_ms,
            "steps": steps,
            "error": error,
        }
        self.log_event(
            event_type="scenario.run",
            request_id=request_id,
            action=scenario,
            payload_summary=body,
            result="ok" if ok else "failed",
            duration_ms=duration_ms,
            error=error,
            raw_response_summary=result,
        )
        return result

    def _append_step(self, steps: list[dict[str, Any]], name: str, started: float, result: dict[str, Any]) -> None:
        steps.append({
            "name": name,
            "ok": bool(result.get("ok")),
            "duration_ms": int((time.time() - started) * 1000),
            "result": _sanitize_payload(result),
        })

    def _scenario_expression(self, steps: list[dict[str, Any]], device_id: Any, expression: str, duration_ms: int) -> None:
        started = time.time()
        result = self.send_expression({"device_id": device_id, "expression": expression, "duration_ms": duration_ms})
        self._append_step(steps, f"expression:{expression}", started, result)

    def _scenario_sound(self, steps: list[dict[str, Any]], device_id: Any, sound: str) -> None:
        if time.time() - self.last_audio_sent_at < AUDIO_COOLDOWN_SECONDS:
            time.sleep(AUDIO_COOLDOWN_SECONDS - (time.time() - self.last_audio_sent_at))
        started = time.time()
        result = self.send_local_sound({"device_id": device_id, "sound": sound, "volume": 0.8})
        self._append_step(steps, f"local_sound:{sound}", started, result)

    def _scenario_motion(self, steps: list[dict[str, Any]], device_id: Any, action: str, action_id: str | None = None) -> None:
        started = time.time()
        params = {"speed": 1.0, "distance_cm": 8, "timeout_ms": 1200}
        if action == "turn":
            params["angle_deg"] = 15
        result = self.send_motion({
            "device_id": device_id,
            "action": action,
            "action_id": action_id,
            "params": params,
            "bench": False,
        })
        self._append_step(steps, f"motion:{action}", started, result)

    def _wait_motion_completed(self, steps: list[dict[str, Any]], action_id: str, timeout_ms: int) -> None:
        started = time.time()
        deadline = started + timeout_ms / 1000.0
        matched = None
        while time.time() < deadline:
            state = read_ws_state(self.runtime_dir).get("state") or {}
            payload = ((state.get("last_motion_completed") or {}).get("payload") or {})
            if payload.get("action_id") == action_id:
                matched = payload
                break
            time.sleep(0.1)
        self._append_step(steps, "wait:motion.completed", started, {
            "ok": matched is not None,
            "payload": matched,
            "action_id": action_id,
        })

    def _scenario_check_file(self, steps: list[dict[str, Any]], filename: str, max_age_ms: int) -> None:
        started = time.time()
        info = _file_info(self.runtime_dir / filename)
        ok = bool(info["exists"] and info["age_ms"] is not None and info["age_ms"] <= max_age_ms)
        self._append_step(steps, f"check:{filename}", started, {"ok": ok, "file": info, "max_age_ms": max_age_ms})

    def _scenario_audio_stats(self, steps: list[dict[str, Any]]) -> None:
        started = time.time()
        result = self.audio_stats()
        self._append_step(steps, "check:audio_stats", started, result)

    def tool_catalog(self) -> dict[str, Any]:
        root = _repo_root()
        tools = {
            "unit-tests": {
                "available": True,
                "label": "unit-tests",
                "description": "python -m unittest discover -s tests -p test_*.py",
                "timeout_sec": 180,
                "command": [sys.executable, "-m", "unittest", "discover", "-s", "tests", "-p", "test_*.py"],
            },
            "dashboard-health": {
                "available": True,
                "label": "dashboard-health",
                "description": "GET http://127.0.0.1:8088/api/dashboard/state",
                "timeout_sec": 8,
                "command": [
                    sys.executable,
                    "-c",
                    "import json,urllib.request; print(urllib.request.urlopen('http://127.0.0.1:8088/api/dashboard/state', timeout=5).read().decode('utf-8')[:2000])",
                ],
            },
            "asr-smoke": {
                "available": (root / "tools" / "demo" / "demo1_usb_mic_to_agent_screen.py").exists(),
                "label": "asr-smoke",
                "description": "Demo1 mock transcript through local screen path, no hardware proof",
                "timeout_sec": 60,
                "command": [
                    sys.executable,
                    "tools/demo/demo1_usb_mic_to_agent_screen.py",
                    "--mock-text",
                    "小安，我有点累",
                    "--once",
                    "--no-screen",
                ],
            },
            "openclaw-decision-only": {
                "available": (root / "tools" / "demo" / "demo1_usb_mic_to_agent_screen.py").exists(),
                "label": "openclaw-decision-only",
                "description": "Demo1 mock transcript to OpenClaw, skip robot /agent execution",
                "timeout_sec": 90,
                "command": [
                    sys.executable,
                    "tools/demo/demo1_usb_mic_to_agent_screen.py",
                    "--mock-text",
                    "小安，我有点累",
                    "--route-openclaw",
                    "--openclaw-decision-only",
                    "--once",
                    "--no-screen",
                ],
            },
            "vision-preflight": {
                "available": (root / "tools" / "prepare_visual_chain_preflight.py").exists(),
                "label": "vision-preflight",
                "description": "Camera-free visual-chain readiness; uses runtime/latest.jpg if available",
                "timeout_sec": 90,
                "command": [
                    sys.executable,
                    "tools/prepare_visual_chain_preflight.py",
                    "--image-path",
                    str(self.runtime_dir / "latest.jpg"),
                    "--check-openclaw",
                ],
            },
        }
        for item in tools.values():
            item["command_preview"] = " ".join(item["command"])
        return tools

    def run_tool(self, body: dict[str, Any]) -> dict[str, Any]:
        tool_id = str(body.get("tool") or "")
        catalog = self.tool_catalog()
        item = catalog.get(tool_id)
        request_id = uuid.uuid4().hex[:12]
        started = time.time()
        if item is None:
            result = {"ok": False, "error": "tool_not_allowed", "tool": tool_id}
        elif not item.get("available"):
            result = {"ok": False, "error": "tool_unavailable", "tool": tool_id}
        else:
            try:
                completed = subprocess.run(
                    item["command"],
                    cwd=_repo_root(),
                    text=True,
                    capture_output=True,
                    timeout=int(item.get("timeout_sec") or 30),
                    shell=False,
                )
            except subprocess.TimeoutExpired as exc:
                result = {
                    "ok": False,
                    "tool": tool_id,
                    "returncode": None,
                    "error": "timeout",
                    "stdout_tail": _tail_lines(exc.stdout or ""),
                    "stderr_tail": _tail_lines(exc.stderr or ""),
                }
            except OSError as exc:
                result = {"ok": False, "tool": tool_id, "error": str(exc)}
            else:
                result = {
                    "ok": completed.returncode == 0,
                    "tool": tool_id,
                    "returncode": completed.returncode,
                    "stdout_tail": _tail_lines(completed.stdout),
                    "stderr_tail": _tail_lines(completed.stderr),
                    "command_preview": item["command_preview"],
                }
        duration_ms = int((time.time() - started) * 1000)
        result["request_id"] = request_id
        result["duration_ms"] = duration_ms
        self.log_event(
            event_type="tool.run",
            request_id=request_id,
            action=tool_id,
            payload_summary={"tool": tool_id},
            result="ok" if result.get("ok") else "failed",
            duration_ms=duration_ms,
            error=result.get("error"),
            raw_response_summary=result,
        )
        return result


def _clamp_float(value: Any, default: float, minimum: float, maximum: float) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        number = default
    return max(minimum, min(number, maximum))


def _clamp_int(value: Any, default: int, minimum: int, maximum: int) -> int:
    try:
        number = int(value)
    except (TypeError, ValueError):
        number = default
    return max(minimum, min(number, maximum))


def _content_type(path: Path) -> str:
    suffix = path.suffix.lower()
    if suffix == ".html":
        return "text/html; charset=utf-8"
    if suffix == ".css":
        return "text/css; charset=utf-8"
    if suffix == ".js":
        return "application/javascript; charset=utf-8"
    if suffix == ".jpg" or suffix == ".jpeg":
        return "image/jpeg"
    return "application/octet-stream"


def _safe_static_path(static_dir: Path, request_path: str) -> Path | None:
    relative = unquote(request_path.removeprefix("/static/"))
    candidate = (static_dir / relative).resolve()
    try:
        candidate.relative_to(static_dir.resolve())
    except ValueError:
        return None
    return candidate


def make_handler(app: IntegrationConsoleApp, verbose: bool = False):
    class ConsoleRequestHandler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:
            parsed = urlsplit(self.path)
            path = parsed.path
            try:
                if path in {"/", "/console"}:
                    self._write_file(app.static_dir / "index.html")
                elif path == "/api/health":
                    self._write_json(app.health())
                elif path == "/api/state":
                    self._write_json(app.state())
                elif path == "/api/latest-image":
                    self._write_file(app.runtime_dir / "latest.jpg", no_cache=True)
                elif path == "/api/visual/state":
                    self._write_json(app.visual_state())
                elif path == "/api/visual/latest-image":
                    self._write_file(app.visual_dir / "latest_annotated.jpg", no_cache=True)
                elif path == "/api/visual/trigger-image":
                    self._write_file(app.visual_dir / "vlm_trigger.jpg", no_cache=True)
                elif path == "/api/fast-demo/visual/latest-image":
                    self._write_file(app.fast_demo_visual_dir / "latest_annotated.jpg", no_cache=True)
                elif path == "/api/fast-demo/visual/trigger-image":
                    self._write_file(app.fast_demo_visual_dir / "vlm_trigger.jpg", no_cache=True)
                elif path == "/api/audio-stats":
                    self._write_json(app.audio_stats())
                elif path == "/api/logs/recent":
                    self._write_json({"ok": True, "events": app.recent_events(limit=EVENT_LIMIT)})
                elif path.startswith("/static/"):
                    static_path = _safe_static_path(app.static_dir, path)
                    if static_path is None:
                        self._write_json({"ok": False, "error": "invalid_static_path"}, status=400)
                    else:
                        self._write_file(static_path)
                else:
                    self._write_json({"ok": False, "error": "not_found"}, status=404)
            except Exception as exc:
                self._write_json({"ok": False, "error": str(exc)}, status=500)

        def do_POST(self) -> None:
            parsed = urlsplit(self.path)
            path = parsed.path
            body = self._read_body()
            try:
                if path == "/api/robot/expression":
                    self._write_json(app.send_expression(body))
                elif path == "/api/robot/motion":
                    self._write_json(app.send_motion(body))
                elif path == "/api/robot/local-sound":
                    self._write_json(app.send_local_sound(body))
                elif path == "/api/robot/tts":
                    self._write_json(app.send_tts(body))
                elif path == "/api/scenario/run":
                    self._write_json(app.run_scenario(body))
                elif path == "/api/links/start":
                    self._write_json(app.start_link(body))
                elif path == "/api/links/stop":
                    self._write_json(app.stop_link(body))
                elif path == "/api/fast-demo/start":
                    self._write_json(app.start_fast_demo(body))
                elif path == "/api/fast-demo/stop":
                    self._write_json(app.stop_fast_demo(body))
                elif path == "/api/fast-demo/execute":
                    self._write_json(app.execute_fast_demo_plan(body))
                elif path == "/api/fast-demo/story/start":
                    self._write_json(app.start_fast_demo_story(body))
                elif path == "/api/fast-demo/story/listen":
                    self._write_json(app.listen_fast_demo_story(body))
                elif path == "/api/fast-demo/dance/listen":
                    self._write_json(app.listen_fast_demo_dance(body))
                elif path == "/api/fast-demo/story/choose":
                    self._write_json(app.choose_fast_demo_story(body))
                elif path == "/api/fast-demo/story/stop":
                    self._write_json(app.stop_fast_demo_story(body))
                elif path == "/api/tools/run":
                    self._write_json(app.run_tool(body))
                elif path == "/api/logs/export":
                    self._write_json(app.export_logs())
                else:
                    self._write_json({"ok": False, "error": "not_found"}, status=404)
            except Exception as exc:
                self._write_json({"ok": False, "error": str(exc)}, status=500)

        def _read_body(self) -> dict[str, Any]:
            length = int(self.headers.get("Content-Length", "0") or "0")
            if length <= 0:
                return {}
            raw = self.rfile.read(min(length, 256 * 1024))
            try:
                data = json.loads(raw.decode("utf-8"))
            except (UnicodeDecodeError, json.JSONDecodeError):
                return {}
            return data if isinstance(data, dict) else {}

        def _write_json(self, data: Any, status: int = 200) -> None:
            payload = _json_bytes(data)
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(payload)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(payload)

        def _write_file(self, path: Path, *, no_cache: bool = True) -> None:
            try:
                payload = path.read_bytes()
            except OSError:
                if path.suffix.lower() in {".jpg", ".jpeg"}:
                    self._write_json({"ok": False, "error": "not_found", "path": str(path)}, status=404)
                else:
                    self._write_json({"ok": False, "error": "not_found"}, status=404)
                return
            self.send_response(200)
            self.send_header("Content-Type", _content_type(path))
            self.send_header("Content-Length", str(len(payload)))
            if no_cache:
                self.send_header("Cache-Control", "no-store, no-cache, must-revalidate")
                self.send_header("Pragma", "no-cache")
            self.end_headers()
            self.wfile.write(payload)

        def log_message(self, format_string: str, *args: Any) -> None:
            if verbose:
                super().log_message(format_string, *args)

    return ConsoleRequestHandler


def create_server(
    host: str,
    port: int,
    *,
    ws_url: str = DEFAULT_WS_URL,
    runtime_dir: str | Path = DEFAULT_RUNTIME_DIR,
    static_dir: str | Path = DEFAULT_STATIC_DIR,
    openclaw_url: str = DEFAULT_OPENCLAW_URL,
    openclaw_workspace: str | Path = DEFAULT_OPENCLAW_WORKSPACE,
    prewarm_voice: bool = False,
    prewarm_fast_demo_tts: bool = False,
    prewarm_fast2_visual: bool = False,
    verbose: bool = False,
) -> ThreadingHTTPServer:
    app = IntegrationConsoleApp(
        host=host,
        port=port,
        ws_url=ws_url,
        runtime_dir=runtime_dir,
        static_dir=static_dir,
        openclaw_url=openclaw_url,
        openclaw_workspace=openclaw_workspace,
        prewarm_voice=prewarm_voice,
        prewarm_fast_demo_tts=prewarm_fast_demo_tts,
        prewarm_fast2_visual=prewarm_fast2_visual,
    )
    handler = make_handler(app, verbose=verbose)
    return ThreadingHTTPServer((host, int(port)), handler)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the Xiao An DK-2500 Integration Console.")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8090)
    parser.add_argument("--ws-url", default=DEFAULT_WS_URL)
    parser.add_argument("--runtime-dir", default=str(DEFAULT_RUNTIME_DIR))
    parser.add_argument("--static-dir", default=str(DEFAULT_STATIC_DIR))
    parser.add_argument("--openclaw-url", default=DEFAULT_OPENCLAW_URL)
    parser.add_argument("--openclaw-workspace", default=str(DEFAULT_OPENCLAW_WORKSPACE))
    parser.add_argument(
        "--no-prewarm-voice",
        action="store_true",
        help="Disable startup ASR prewarm for the local microphone runtime.",
    )
    parser.add_argument(
        "--no-prewarm-fast-demo-tts",
        action="store_true",
        help="Disable startup Fast Demo TTS cache preparation.",
    )
    parser.add_argument(
        "--no-prewarm-fast2-visual",
        action="store_true",
        help="Disable startup Fast2 visual/VLM runtime preload.",
    )
    parser.add_argument("--verbose", action="store_true")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    server = create_server(
        host=args.host,
        port=args.port,
        ws_url=args.ws_url,
        runtime_dir=args.runtime_dir,
        static_dir=args.static_dir,
        openclaw_url=args.openclaw_url,
        openclaw_workspace=args.openclaw_workspace,
        prewarm_voice=not args.no_prewarm_voice,
        prewarm_fast_demo_tts=not args.no_prewarm_fast_demo_tts,
        prewarm_fast2_visual=not args.no_prewarm_fast2_visual,
        verbose=args.verbose,
    )
    try:
        if args.verbose:
            host, port = server.server_address[:2]
            print(f"Xiao-An Integration Console listening on http://{host}:{port}/console")
        server.serve_forever()
    except KeyboardInterrupt:
        return 0
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
