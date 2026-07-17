"""Shared work-mode state and coarse episode arbitration for Xiao An."""

from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import time
from typing import Any, Iterator
import uuid


SCHEMA_VERSION = "xiaoan.work_mode.v1"
DEFAULT_WORK_MODE_STATE_PATH = Path("runtime") / "work_mode_state.json"
DEFAULT_COOLDOWN_SECONDS = 0.8


def default_work_mode_state(*, system_enabled: bool = True) -> dict[str, Any]:
    now = _now_iso()
    return {
        "schema_version": SCHEMA_VERSION,
        "updated_at": now,
        "system_enabled": bool(system_enabled),
        "mic_device_open": bool(system_enabled),
        "mic_recognition_enabled": bool(system_enabled),
        "camera_capture_enabled": True,
        "episode_state": "idle",
        "active_chain": None,
        "active_run_id": None,
        "cooldown_until": None,
        "last_episode": None,
    }


@dataclass(frozen=True)
class EpisodeLease:
    acquired: bool
    run_id: str | None
    chain: str | None
    reason: str = ""
    state: dict[str, Any] | None = None


class WorkModeStore:
    """Small JSON-backed state store used by console and runtime processes."""

    def __init__(
        self,
        path: str | Path | None = None,
        *,
        default_system_enabled: bool = True,
        cooldown_seconds: float = DEFAULT_COOLDOWN_SECONDS,
        ignore_existing: bool = False,
    ):
        self.path = Path(path or os.environ.get("XIAOAN_WORK_MODE_STATE_PATH") or DEFAULT_WORK_MODE_STATE_PATH)
        self.default_system_enabled = bool(default_system_enabled)
        self.cooldown_seconds = float(cooldown_seconds)
        self.lock_path = self.path.with_suffix(self.path.suffix + ".lock")
        self.ignore_existing = bool(ignore_existing)

    @classmethod
    def from_env(cls) -> "WorkModeStore":
        path = os.environ.get("XIAOAN_WORK_MODE_STATE_PATH")
        if path:
            return cls(path)
        return cls(ignore_existing=True)

    def snapshot(self) -> dict[str, Any]:
        if self.ignore_existing or not self.path.exists():
            state = default_work_mode_state(system_enabled=self.default_system_enabled)
            state["persisted"] = False
            state["path"] = str(self.path)
            return state
        with self._locked():
            state = self._read_unlocked()
        state["persisted"] = True
        state["path"] = str(self.path)
        return state

    def update_controls(
        self,
        *,
        system_enabled: bool | None = None,
        mic_recognition_enabled: bool | None = None,
        camera_capture_enabled: bool | None = None,
    ) -> dict[str, Any]:
        with self._locked():
            state = self._read_unlocked()
            if system_enabled is not None:
                enabled = bool(system_enabled)
                state["system_enabled"] = enabled
                state["mic_device_open"] = enabled
                if not enabled:
                    state["mic_recognition_enabled"] = False
                    state["episode_state"] = "idle"
                    state["active_chain"] = None
                    state["active_run_id"] = None
                    state["cooldown_until"] = None
            if mic_recognition_enabled is not None:
                state["mic_recognition_enabled"] = bool(mic_recognition_enabled) and bool(state.get("system_enabled"))
            if camera_capture_enabled is not None:
                state["camera_capture_enabled"] = bool(camera_capture_enabled)
            state["updated_at"] = _now_iso()
            self._write_unlocked(state)
            return dict(state)

    def acquire_episode(
        self,
        *,
        chain: str,
        source: str,
        text: str | None = None,
        requires_mic_recognition: bool = False,
    ) -> EpisodeLease:
        run_id = f"{chain}-{uuid.uuid4().hex[:10]}"
        with self._locked():
            state = self._read_unlocked()
            if not state.get("system_enabled", True):
                return EpisodeLease(False, None, chain, "system_disabled", dict(state))
            if requires_mic_recognition and not state.get("mic_recognition_enabled", True):
                return EpisodeLease(False, None, chain, "mic_recognition_disabled", dict(state))
            cooldown_until = _parse_ts(state.get("cooldown_until"))
            now = time.time()
            if cooldown_until is not None and cooldown_until > now:
                return EpisodeLease(False, None, chain, "cooldown", dict(state))
            if state.get("episode_state") == "running" and state.get("active_run_id"):
                return EpisodeLease(False, None, chain, "busy", dict(state))
            state.update({
                "updated_at": _now_iso(),
                "episode_state": "running",
                "active_chain": chain,
                "active_run_id": run_id,
                "cooldown_until": None,
                "last_episode": {
                    "run_id": run_id,
                    "chain": chain,
                    "source": source,
                    "text": (text or "")[:160],
                    "started_at": _now_iso(),
                    "status": "running",
                },
            })
            self._write_unlocked(state)
            return EpisodeLease(True, run_id, chain, "acquired", dict(state))

    def release_episode(
        self,
        run_id: str | None,
        *,
        status: str = "completed",
        result: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        if not run_id:
            return self.snapshot()
        with self._locked():
            state = self._read_unlocked()
            if state.get("active_run_id") != run_id:
                return dict(state)
            last = state.get("last_episode") if isinstance(state.get("last_episode"), dict) else {}
            last.update({
                "status": status,
                "ended_at": _now_iso(),
            })
            if result is not None:
                last["result"] = _compact_result(result)
            state.update({
                "updated_at": _now_iso(),
                "episode_state": "cooldown",
                "active_chain": None,
                "active_run_id": None,
                "cooldown_until": datetime.fromtimestamp(
                    time.time() + self.cooldown_seconds,
                    timezone.utc,
                ).isoformat(),
                "last_episode": last,
            })
            self._write_unlocked(state)
            return dict(state)

    @contextmanager
    def _locked(self) -> Iterator[None]:
        self.lock_path.parent.mkdir(parents=True, exist_ok=True)
        with self.lock_path.open("a+", encoding="utf-8") as lock_file:
            try:
                import fcntl

                fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX)
                yield
            finally:
                try:
                    import fcntl

                    fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)
                except Exception:
                    pass

    def _read_unlocked(self) -> dict[str, Any]:
        if self.ignore_existing:
            return default_work_mode_state(system_enabled=self.default_system_enabled)
        try:
            raw = self.path.read_text(encoding="utf-8")
            data = json.loads(raw)
        except (FileNotFoundError, json.JSONDecodeError, OSError):
            return default_work_mode_state(system_enabled=self.default_system_enabled)
        if not isinstance(data, dict) or data.get("schema_version") != SCHEMA_VERSION:
            return default_work_mode_state(system_enabled=self.default_system_enabled)
        state = default_work_mode_state(system_enabled=self.default_system_enabled)
        state.update(data)
        return state

    def _write_unlocked(self, state: dict[str, Any]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(self.path.suffix + ".tmp")
        tmp.write_text(json.dumps(state, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        tmp.replace(self.path)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _parse_ts(value: Any) -> float | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00")).timestamp()
    except ValueError:
        return None


def _compact_result(result: dict[str, Any]) -> dict[str, Any]:
    return {
        "route": result.get("route"),
        "reason": result.get("reason"),
        "handled": result.get("handled"),
        "ok": result.get("ok"),
    }
