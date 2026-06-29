"""Standard-library dashboard server for the Xiao An 7-inch Dock screen."""

from __future__ import annotations

import argparse
import json
import socket
import time
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import unquote, urlsplit

DEFAULT_DATA_DIR = Path(__file__).with_name("data")
DEFAULT_STATIC_DIR = Path(__file__).with_name("static")
DEFAULT_RUNTIME_DIR = Path("runtime")
TRIGGER_LIMIT = 3
RECENT_SECONDS = 10

PIPELINE_DEFAULTS = {
    "current_state": "idle",
    "current_trigger": None,
    "robot": "unknown",
    "base_station": "ready",
    "agent": "unknown",
    "action": "waiting",
}

VALID_TRIGGER_SOURCES = {
    "schedule",
    "todo",
    "alarm",
    "emotion",
    "voice",
    "manual",
    "agent",
    "system",
}

VALID_TRIGGER_STATUSES = {
    "idle",
    "triggered",
    "processing",
    "executing",
    "acked",
    "completed",
    "failed",
    "timeout",
}


def _now_iso() -> str:
    return datetime.now().replace(microsecond=0).isoformat()


def _load_json_file(path: Path, fallback: dict[str, Any]) -> dict[str, Any]:
    try:
        raw = path.read_text(encoding="utf-8")
        data = json.loads(raw)
    except (OSError, json.JSONDecodeError):
        return dict(fallback)
    if not isinstance(data, dict):
        return dict(fallback)
    return data


def _latest_session() -> dict[str, Any] | None:
    try:
        from base_station.ws_server import server as ws_server
    except Exception:
        return None

    sessions = getattr(ws_server, "sessions", {})
    if not sessions:
        return None
    return max(
        sessions.values(),
        key=lambda item: float(item.get("last_hb") or 0),
    )


def _seconds_ago_from_mtime(path: Path) -> float | None:
    try:
        return max(0.0, time.time() - path.stat().st_mtime)
    except OSError:
        return None


def _format_age(seconds: float | None) -> str | None:
    if seconds is None:
        return None
    if seconds < 1:
        return "just now"
    if seconds < 60:
        return f"{int(seconds)}s ago"
    minutes = int(seconds // 60)
    if minutes < 60:
        return f"{minutes}m ago"
    return f"{int(minutes // 60)}h ago"


def _read_audio_stats(runtime_dir: Path) -> dict[str, Any] | None:
    data = _load_json_file(runtime_dir / "audio_stats.json", {})
    return data or None


def _timestamp_age_seconds(value: Any) -> float | None:
    try:
        timestamp = float(value)
    except (TypeError, ValueError):
        return None
    if timestamp <= 0:
        return None
    return max(0.0, time.time() - timestamp)


def _camera_state(runtime_dir: Path, robot_status: dict[str, Any] | None) -> str:
    status_camera = (robot_status or {}).get("camera")
    if isinstance(status_camera, str) and status_camera:
        if status_camera.lower() in {"cam_ok", "active", "streaming"}:
            return "active"
        if status_camera.lower() in {"cam_off", "idle", "disabled"}:
            return "idle"

    latest_age = _seconds_ago_from_mtime(runtime_dir / "latest.jpg")
    if latest_age is None:
        return "unknown"
    return "active" if latest_age <= RECENT_SECONDS else "idle"


def _audio_state(runtime_dir: Path, audio_stats: dict[str, Any] | None) -> str:
    if audio_stats:
        latest_age = _timestamp_age_seconds(audio_stats.get("updated_at"))
        if latest_age is not None:
            return "active" if latest_age <= RECENT_SECONDS else "idle"
    if (runtime_dir / "latest_audio.pcm").exists():
        return "idle"
    return "unknown"


def _normalize_pipeline(raw: dict[str, Any]) -> dict[str, Any]:
    pipeline = dict(PIPELINE_DEFAULTS)
    raw_pipeline = raw.get("pipeline")
    if isinstance(raw_pipeline, dict):
        for key in PIPELINE_DEFAULTS:
            if key in raw_pipeline:
                pipeline[key] = raw_pipeline[key]
    pipeline["last_updated_at"] = str(
        (raw_pipeline or {}).get("last_updated_at") or _now_iso()
    )
    return pipeline


def _normalize_trigger(item: Any) -> dict[str, str] | None:
    if not isinstance(item, dict):
        return None

    source = str(item.get("source") or "system").lower()
    if source not in VALID_TRIGGER_SOURCES:
        source = "system"

    status = str(item.get("status") or "idle").lower()
    if status not in VALID_TRIGGER_STATUSES:
        status = "idle"

    return {
        "time": str(item.get("time") or "--:--"),
        "source": source,
        "title": str(item.get("title") or "未命名觸發"),
        "chain": str(item.get("chain") or "Unknown → Dashboard"),
        "status": status,
        "detail": str(item.get("detail") or ""),
    }


def _normalize_triggers(raw: dict[str, Any]) -> list[dict[str, str]]:
    raw_triggers = raw.get("triggers", [])
    if not isinstance(raw_triggers, list):
        return []

    triggers: list[dict[str, str]] = []
    for item in raw_triggers:
        normalized = _normalize_trigger(item)
        if normalized is not None:
            triggers.append(normalized)
        if len(triggers) >= TRIGGER_LIMIT:
            break
    return triggers


def _host_ip() -> str:
    try:
        return socket.gethostbyname(socket.gethostname())
    except OSError:
        return "unknown"


def _build_runtime_state(
    pipeline: dict[str, Any],
    runtime_dir: Path,
) -> dict[str, Any]:
    session = _latest_session()
    robot_status = session.get("status") if session else None
    if not isinstance(robot_status, dict):
        robot_status = {}

    latest_image_age = _seconds_ago_from_mtime(runtime_dir / "latest.jpg")
    audio_stats = _read_audio_stats(runtime_dir)
    audio_latest_path = runtime_dir / "latest_audio.pcm"

    robot_online = session is not None
    camera = _camera_state(runtime_dir, robot_status)
    audio = _audio_state(runtime_dir, audio_stats)

    return {
        "system": {
            "name": "Xiao-An Dock",
            "mode": pipeline.get("current_state", "idle"),
            "ip": _host_ip(),
            "base_station": "online",
        },
        "robot": {
            "online": robot_online,
            "status": "connected" if robot_online else "offline",
            "last_seen": session.get("last_hb") if session else None,
            "control": "connected" if robot_online else "offline",
            "camera": camera,
            "audio": audio,
            "battery": session.get("battery") if session else None,
        },
        "agent": {
            "openclaw": "unknown",
            "runtime": str(pipeline.get("agent") or "unknown"),
            "emotion_pipeline": (
                "running"
                if pipeline.get("current_state") in {"processing", "executing"}
                else "idle"
            ),
        },
        "perception": {
            "latest_image_exists": latest_image_age is not None,
            "latest_image_updated_ago": _format_age(latest_image_age),
            "latest_audio_exists": audio_latest_path.exists(),
            "latest_audio_updated_ago": _format_age(
                _timestamp_age_seconds((audio_stats or {}).get("updated_at"))
            ),
        },
        "resources": {
            "cpu_percent": None,
            "ram_percent": None,
        },
    }


def load_dashboard_state(
    data_dir: str | Path = DEFAULT_DATA_DIR,
    runtime_dir: str | Path = DEFAULT_RUNTIME_DIR,
) -> dict[str, Any]:
    """Load dashboard health, pipeline, and recent trigger state."""

    data_path = Path(data_dir)
    runtime_path = Path(runtime_dir)
    raw = _load_json_file(data_path / "triggers.json", {})
    pipeline = _normalize_pipeline(raw)
    state = _build_runtime_state(pipeline, runtime_path)
    state["pipeline"] = pipeline
    state["triggers"] = _normalize_triggers(raw)
    return state


def load_today_data(data_dir: str | Path = DEFAULT_DATA_DIR) -> dict[str, Any]:
    return _load_json_file(
        Path(data_dir) / "today.json",
        {"schedules": [], "todos": [], "alarms": []},
    )


def _json_bytes(data: Any) -> bytes:
    return json.dumps(data, ensure_ascii=False, indent=2).encode("utf-8")


def _content_type(path: Path) -> str:
    suffix = path.suffix.lower()
    if suffix == ".html":
        return "text/html; charset=utf-8"
    if suffix == ".css":
        return "text/css; charset=utf-8"
    if suffix == ".js":
        return "application/javascript; charset=utf-8"
    if suffix == ".json":
        return "application/json; charset=utf-8"
    return "application/octet-stream"


def _safe_static_path(static_dir: Path, request_path: str) -> Path | None:
    relative = unquote(request_path.removeprefix("/static/"))
    candidate = (static_dir / relative).resolve()
    try:
        candidate.relative_to(static_dir.resolve())
    except ValueError:
        return None
    return candidate


def make_handler(
    data_dir: Path,
    static_dir: Path,
    runtime_dir: Path,
    verbose: bool = False,
):
    class DashboardRequestHandler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:
            parsed = urlsplit(self.path)
            path = parsed.path

            if path in {"/", "/dashboard"}:
                self._write_file(static_dir / "dashboard.html")
                return
            if path == "/api/dashboard/state":
                self._write_json(load_dashboard_state(data_dir, runtime_dir))
                return
            if path == "/api/dashboard/today":
                self._write_json(load_today_data(data_dir))
                return
            if path == "/api/health":
                self._write_json({"status": "ok"})
                return
            if path.startswith("/static/"):
                static_path = _safe_static_path(static_dir, path)
                if static_path is None:
                    self._write_json({"error": "invalid_static_path"}, status=400)
                    return
                self._write_file(static_path)
                return

            self._write_json({"error": "not_found"}, status=404)

        def _write_json(self, data: Any, status: int = 200) -> None:
            payload = _json_bytes(data)
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(payload)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(payload)

        def _write_file(self, path: Path) -> None:
            try:
                payload = path.read_bytes()
            except OSError:
                self._write_json({"error": "not_found"}, status=404)
                return
            self.send_response(200)
            self.send_header("Content-Type", _content_type(path))
            self.send_header("Content-Length", str(len(payload)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(payload)

        def log_message(self, format_string: str, *args: Any) -> None:
            if verbose:
                super().log_message(format_string, *args)

    return DashboardRequestHandler


def create_server(
    host: str,
    port: int,
    data_dir: str | Path = DEFAULT_DATA_DIR,
    static_dir: str | Path = DEFAULT_STATIC_DIR,
    runtime_dir: str | Path = DEFAULT_RUNTIME_DIR,
    verbose: bool = False,
) -> ThreadingHTTPServer:
    handler = make_handler(
        data_dir=Path(data_dir),
        static_dir=Path(static_dir),
        runtime_dir=Path(runtime_dir),
        verbose=verbose,
    )
    return ThreadingHTTPServer((host, int(port)), handler)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the Xiao An Dock dashboard.")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8088)
    parser.add_argument("--data-dir", default=str(DEFAULT_DATA_DIR))
    parser.add_argument("--static-dir", default=str(DEFAULT_STATIC_DIR))
    parser.add_argument("--runtime-dir", default=str(DEFAULT_RUNTIME_DIR))
    parser.add_argument("--verbose", action="store_true")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    server = create_server(
        host=args.host,
        port=args.port,
        data_dir=args.data_dir,
        static_dir=args.static_dir,
        runtime_dir=args.runtime_dir,
        verbose=args.verbose,
    )
    try:
        if args.verbose:
            host, port = server.server_address[:2]
            print(f"Xiao-An Dock dashboard listening on http://{host}:{port}/dashboard")
        server.serve_forever()
    except KeyboardInterrupt:
        return 0
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
