"""Standard-library Integration Console for DK-2500 bring-up.

Run from the repository root:
    python -m base_station.integration_console.console_server --host 0.0.0.0 --port 8090
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import signal
import socket
import subprocess
import sys
import time
import uuid
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Callable
from urllib.parse import unquote, urlparse, urlsplit

DEFAULT_RUNTIME_DIR = Path("runtime")
DEFAULT_STATIC_DIR = Path(__file__).with_name("static")
DEFAULT_WS_URL = "ws://127.0.0.1:8765/agent"
DEFAULT_OPENCLAW_URL = "ws://127.0.0.1:18789"
DEFAULT_OPENCLAW_WORKSPACE = Path.home() / ".openclaw" / "workspace-xiaoan-runtime"
OPENCLAW_DASHBOARD_SCHEMA = "xiaoan.dashboard.v1"
EVENT_LIMIT = 200
STATE_EVENT_LIMIT = 50
AUDIO_COOLDOWN_SECONDS = 2.5
FRESH_IMAGE_MS = 3000
FRESH_AUDIO_MS = 5000
FRESH_VISUAL_MS = 3000
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


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


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
        }

    def audio_stats(self) -> dict[str, Any]:
        path = self.runtime_dir / "audio_stats.json"
        data, error = _load_json_file(path)
        if data is None:
            return {"ok": False, "reason": error or "not_found", "path": str(path)}
        return {"ok": True, "path": str(path), "audio_stats": data}

    def visual_state(self) -> dict[str, Any]:
        path = self.visual_dir / "latest_state.json"
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
                    "latest_image": _file_info(self.visual_dir / "latest_annotated.jpg"),
                    "trigger_image": _file_info(self.visual_dir / "vlm_trigger.jpg"),
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
                "latest_image": _file_info(self.visual_dir / "latest_annotated.jpg"),
                "trigger_image": _file_info(self.visual_dir / "vlm_trigger.jpg"),
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
            for link in ("link1", "link2", "link3")
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

    def link_command(self, link: str) -> list[str]:
        if link in {"link1", "link3"}:
            duration = self._env_text(f"XIAOAN_{link.upper()}_MIC_WINDOW", "6.0")
            return [
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
                *(["--disable-companion-fast-path"] if link == "link1" else []),
                "--verbose",
            ]
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
                self._env_text("XIAOAN_LINK2_VLM_BACKEND", "fake"),
                "--visual-trace-dir",
                str(self.visual_dir),
                "--visual-trace-fps",
                self._env_text("XIAOAN_LINK2_VISUAL_TRACE_FPS", "1.0"),
                "--verbose",
            ]
            if self._env_truthy("XIAOAN_LINK2_FORCE_VLM", False):
                command.append("--force-vlm")
            return command
        raise ValueError(f"unsupported_link:{link}")

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

        return {
            "ok": True,
            "current_time": _now_iso(),
            "console": self.health(),
            "ws_server": ws_state,
            "robot": robot,
            "media": media,
            "asr": asr,
            "link_voice": link_voice,
            "openclaw": self.openclaw_status(),
            "openclaw_dashboard": dashboard_state,
            "visual": visual_state,
            "links": links,
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
        link1_audio_fresh = link1_running and (link1_voice_fresh or _fresh(link1_audio, 30000))
        link3_audio_fresh = link3_running and (link3_voice_fresh or _fresh(link3_audio, 30000))
        camera_fresh = _fresh(latest_image, FRESH_IMAGE_MS)
        visual_fresh = bool(visual.get("ok") and visual.get("age_ms") is not None and int(visual.get("age_ms") or 0) <= FRESH_VISUAL_MS)
        executed_actions = execution.get("executed_actions") if isinstance(execution.get("executed_actions"), list) else []

        link1_steps = [
            _step("voice runtime", link1_running, (processes.get("link1") or {}).get("pid")),
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
        ]
        link3_steps = [
            _step("voice runtime", link3_running, (processes.get("link3") or {}).get("pid")),
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
                "status": self._status_from_steps(link1_steps) if link1_running else "idle",
                "done": all(step["ok"] for step in link1_steps),
                "steps": link1_steps,
                "asr_text": link1_asr_text,
                "openclaw_text": link1_openclaw_text,
                "dashboard_text": dashboard_text,
                "robot_execution": self._robot_execution_summary(robot),
                "voice": link1_voice,
            },
            "link2": {
                "status": self._status_from_steps(link2_steps) if link2_running else "idle",
                "done": all(step["ok"] for step in link2_steps),
                "steps": link2_steps,
                "visual_freshness": visual.get("freshness"),
            },
            "link3": {
                "status": self._status_from_steps(link3_steps) if link3_running else "idle",
                "done": all(step["ok"] for step in link3_steps),
                "steps": link3_steps,
                "asr_text": link3_asr_text,
                "fast_response": self._robot_execution_summary(robot),
                "follow_up_text": spoken_text or link3_openclaw_text,
                "voice": link3_voice,
            },
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
        try:
            async with websockets.connect(self.ws_url, open_timeout=3) as websocket:
                await asyncio.wait_for(
                    websocket.send(json.dumps(message, ensure_ascii=False)),
                    timeout=3,
                )
                raw_ack = await asyncio.wait_for(websocket.recv(), timeout=4)
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
        speed = _clamp_float(raw_params.get("speed"), 0.56, 0.0 if bench else 0.52, 1.0 if bench else 0.56)
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
            "duration_ms": _clamp_int(body.get("duration_ms"), 3000, 500, 8000),
        }
        result = self.send_agent_command(payload, action="tts", event_type="robot.tts")
        if result.get("ok"):
            self.last_audio_sent_at = time.time()
        return result

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
        params = {"speed": 0.56, "distance_cm": 8, "timeout_ms": 1200}
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
