"""Local microphone capture helpers for voice runtime ASR input."""

from __future__ import annotations

import re
import shutil
import subprocess
import wave
from pathlib import Path
from typing import Any


def import_pyaudio():
    try:
        import pyaudio  # type: ignore
    except ImportError as exc:
        raise RuntimeError(
            "PyAudio is required for direct microphone capture. "
            "Install base_station/requirements-audio.txt, or use an arecord device."
        ) from exc
    return pyaudio


def _pyaudio_input_devices() -> list[dict[str, Any]]:
    try:
        pyaudio = import_pyaudio()
    except RuntimeError:
        return []

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
        return []
    return parse_arecord_devices(result.stdout)


def list_input_devices() -> list[dict[str, Any]]:
    devices = _pyaudio_input_devices()
    devices.extend(_arecord_input_devices())
    if devices:
        return devices
    raise RuntimeError(
        "No audio input devices found through PyAudio or arecord. "
        "Check the microphone connection."
    )


def choose_input_device(
    devices: list[dict[str, Any]],
    requested: str | None = None,
) -> dict[str, Any]:
    if not devices:
        raise RuntimeError("No audio input devices found.")

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
            if lowered in str(device.get("name", "")).lower()
        ]
        if matches:
            return matches[0]
        raise RuntimeError(f"Audio input device name not found: {requested_text}")

    preferred_markers = ("usb", "microphone", "mic", "麦克风")
    preferred = [
        device
        for device in devices
        if any(marker in str(device.get("name", "")).lower() for marker in preferred_markers)
    ]
    return preferred[0] if preferred else devices[0]


def recording_sample_rate(device: dict[str, Any], requested_sample_rate: int) -> int:
    if device.get("backend") != "pyaudio":
        return requested_sample_rate
    default_rate = int(float(device.get("default_sample_rate") or 0))
    return default_rate if default_rate > 0 else requested_sample_rate


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


class PersistentWavRecorder:
    """Keep the microphone device open and write fixed windows to WAV files."""

    def __init__(
        self,
        *,
        device: dict[str, Any],
        sample_rate: int = 16000,
        channels: int = 1,
        frames_per_buffer: int = 1024,
    ):
        self.device = device
        self.sample_rate = int(sample_rate)
        self.channels = int(channels)
        self.frames_per_buffer = int(frames_per_buffer)
        self._pyaudio = None
        self._audio = None
        self._stream = None
        self._process: subprocess.Popen[bytes] | None = None

    def __enter__(self) -> "PersistentWavRecorder":
        if self.device.get("backend") == "arecord":
            self._open_arecord()
            return self
        self._open_pyaudio()
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.close()

    def record_window(self, output_path: str | Path, duration_seconds: float) -> Path:
        pcm = self.read_window(duration_seconds)
        target = Path(output_path)
        target.parent.mkdir(parents=True, exist_ok=True)
        with wave.open(str(target), "wb") as wav:
            wav.setnchannels(self.channels)
            wav.setsampwidth(2)
            wav.setframerate(self.sample_rate)
            wav.writeframes(pcm)
        return target

    def discard_window(self, duration_seconds: float) -> int:
        return len(self.read_window(duration_seconds))

    def read_window(self, duration_seconds: float) -> bytes:
        frame_count = max(1, int(round(self.sample_rate * float(duration_seconds))))
        if self.device.get("backend") == "arecord":
            return self._read_arecord_bytes(frame_count * self.channels * 2)
        if self._stream is None:
            raise RuntimeError("PersistentWavRecorder is not open.")
        chunks = []
        remaining = frame_count
        while remaining > 0:
            chunk_frames = min(self.frames_per_buffer, remaining)
            chunks.append(self._stream.read(chunk_frames, exception_on_overflow=False))
            remaining -= chunk_frames
        return b"".join(chunks)

    def close(self) -> None:
        if self._stream is not None:
            try:
                self._stream.stop_stream()
            finally:
                self._stream.close()
                self._stream = None
        if self._audio is not None:
            self._audio.terminate()
            self._audio = None
        if self._process is not None:
            process = self._process
            self._process = None
            process.terminate()
            try:
                process.wait(timeout=2)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=2)

    def _open_pyaudio(self) -> None:
        self._pyaudio = import_pyaudio()
        self._audio = self._pyaudio.PyAudio()
        self._stream = self._audio.open(
            format=self._pyaudio.paInt16,
            channels=self.channels,
            rate=self.sample_rate,
            input=True,
            input_device_index=int(self.device["index"]),
            frames_per_buffer=self.frames_per_buffer,
        )

    def _open_arecord(self) -> None:
        if shutil.which("arecord") is None:
            raise RuntimeError("arecord is not installed; cannot record without PyAudio.")
        command = [
            "arecord",
            "-D",
            str(self.device["device_id"]),
            "-f",
            "S16_LE",
            "-r",
            str(self.sample_rate),
            "-c",
            str(self.channels),
            "-t",
            "raw",
            "-q",
        ]
        self._process = subprocess.Popen(
            command,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )

    def _read_arecord_bytes(self, byte_count: int) -> bytes:
        if self._process is None or self._process.stdout is None:
            raise RuntimeError("Persistent arecord recorder is not open.")
        chunks = []
        remaining = int(byte_count)
        while remaining > 0:
            chunk = self._process.stdout.read(remaining)
            if not chunk:
                stderr = b""
                if self._process.stderr is not None:
                    stderr = self._process.stderr.read(4096)
                raise RuntimeError(f"arecord stream ended: {stderr.decode('utf-8', errors='ignore').strip()}")
            chunks.append(chunk)
            remaining -= len(chunk)
        return b"".join(chunks)


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
