"""Voice activity detection interfaces and local test backends."""

from __future__ import annotations

import struct
import warnings


def _audio_duration(audio_clip: dict) -> int:
    return int(audio_clip.get("duration_ms") or 0)


class VoiceActivitySource:
    """Base interface for voice activity detectors."""

    def is_speech(self, pcm_frame: bytes, sample_rate: int = 16000) -> bool:
        raise NotImplementedError("Voice activity detection is not implemented.")


class FakeVoiceActivityDetector(VoiceActivitySource):
    """Return pre-defined speech flags one by one."""

    def __init__(self, pattern: list[bool] | None = None):
        self.pattern = list(pattern or [])
        self._index = 0

    def is_speech(self, pcm_frame: bytes, sample_rate: int = 16000) -> bool:
        if self._index >= len(self.pattern):
            return False
        value = bool(self.pattern[self._index])
        self._index += 1
        return value


class FakeVADBackend:
    """Mock VAD backend for software smoke tests."""

    def __init__(self, pattern: str = "speech"):
        if pattern not in {"speech", "silence"}:
            raise ValueError("Fake VAD pattern must be 'speech' or 'silence'.")
        self.pattern = pattern

    def analyze(self, audio_clip: dict) -> dict:
        speech = self.pattern == "speech"
        return {
            "speech_detected": speech,
            "confidence": 0.9 if speech else 0.95,
            "start_ms": 0 if speech else None,
            "end_ms": _audio_duration(audio_clip) if speech else None,
            "reason": "fake_speech" if speech else "fake_silence",
        }


class EnergyVADBackend:
    """Simple local WAV energy VAD with no model dependency."""

    def __init__(self, threshold: float = 0.01):
        if threshold < 0:
            raise ValueError("Energy VAD threshold must be non-negative.")
        self.threshold = threshold

    def analyze(self, audio_clip: dict) -> dict:
        pcm_bytes = audio_clip.get("pcm_bytes") or b""
        sample_width = int(audio_clip.get("sample_width") or 2)
        channels = max(1, int(audio_clip.get("channels") or 1))
        rms = self._rms_energy(pcm_bytes, sample_width=sample_width)
        speech = rms >= self.threshold
        return {
            "speech_detected": speech,
            "confidence": min(1.0, max(0.0, rms / max(self.threshold, 1e-9))) if speech else 0.0,
            "start_ms": 0 if speech else None,
            "end_ms": _audio_duration(audio_clip) if speech else None,
            "reason": "energy_threshold",
            "energy": rms,
            "channels": channels,
        }

    @staticmethod
    def _rms_energy(pcm_bytes: bytes, sample_width: int) -> float:
        if not pcm_bytes:
            return 0.0
        if sample_width == 2:
            usable = len(pcm_bytes) - (len(pcm_bytes) % 2)
            if usable <= 0:
                return 0.0
            values = struct.unpack("<" + "h" * (usable // 2), pcm_bytes[:usable])
            if not values:
                return 0.0
            mean_square = sum((sample / 32768.0) ** 2 for sample in values) / len(values)
            return mean_square ** 0.5
        if sample_width == 1:
            values = [(sample - 128) / 128.0 for sample in pcm_bytes]
            mean_square = sum(sample * sample for sample in values) / len(values)
            return mean_square ** 0.5
        raise RuntimeError(f"Energy VAD supports 8-bit or 16-bit PCM WAV, got sample_width={sample_width}.")


class SileroVADBackend:
    """Silero VAD backend using the `silero-vad` pip package."""

    _model = None

    def __init__(self, model_path: str | None = None, threshold: float = 0.5):
        self.model_path = model_path
        self.threshold = threshold
        self._warned_model_path_ignored = False

    def analyze(self, audio_clip: dict) -> dict:
        if self.model_path and not self._warned_model_path_ignored:
            warnings.warn(
                "Silero VAD uses the silero-vad pip package model; --vad-model-path is recorded but ignored.",
                RuntimeWarning,
                stacklevel=2,
            )
            self._warned_model_path_ignored = True

        sample_rate = int(audio_clip.get("sample_rate") or 0)
        if sample_rate not in {8000, 16000}:
            raise RuntimeError(
                "Silero VAD supports 8000 Hz or 16000 Hz PCM WAV audio. "
                f"Got sample_rate={sample_rate}; convert the file to 16 kHz mono PCM WAV."
            )

        sample_width = int(audio_clip.get("sample_width") or 0)
        channels = max(1, int(audio_clip.get("channels") or 1))
        wav = self._pcm_to_float_tensor(
            audio_clip.get("pcm_bytes") or b"",
            sample_width=sample_width,
            channels=channels,
        )

        try:
            from silero_vad import get_speech_timestamps, load_silero_vad
        except ImportError as exc:
            raise ImportError(
                "Silero VAD requires the silero-vad package installed in the project .venv. "
                "Install it with: .venv/bin/python -m pip install -r base_station/requirements-audio.txt"
            ) from exc

        model = self._load_model(load_silero_vad)
        try:
            timestamps = get_speech_timestamps(
                wav,
                model,
                sampling_rate=sample_rate,
                return_seconds=True,
                threshold=self.threshold,
            )
        except Exception as exc:
            raise RuntimeError(f"Silero VAD inference failed: {type(exc).__name__}: {exc}") from exc

        normalized_timestamps = [dict(item) for item in (timestamps or [])]
        speech = bool(normalized_timestamps)
        start_ms = int(round(float(normalized_timestamps[0]["start"]) * 1000)) if speech else None
        end_ms = int(round(float(normalized_timestamps[-1]["end"]) * 1000)) if speech else None
        return {
            "speech_detected": speech,
            "confidence": 1.0 if speech else 0.0,
            "start_ms": start_ms,
            "end_ms": end_ms,
            "reason": "silero",
            "backend": "silero",
            "timestamps": normalized_timestamps,
            "sample_rate": sample_rate,
            "threshold": self.threshold,
            "model_path": self.model_path,
        }

    @classmethod
    def _load_model(cls, load_silero_vad):
        if cls._model is None:
            try:
                cls._model = load_silero_vad()
            except Exception as exc:
                raise RuntimeError(f"Silero VAD model load failed: {type(exc).__name__}: {exc}") from exc
        return cls._model

    @staticmethod
    def _pcm_to_float_tensor(pcm_bytes: bytes, *, sample_width: int, channels: int):
        if sample_width != 2:
            raise RuntimeError(f"Silero VAD supports 16-bit PCM WAV only, got sample_width={sample_width}.")

        try:
            import torch
        except ImportError as exc:
            raise ImportError("Silero VAD requires torch installed in the project .venv.") from exc

        if not pcm_bytes:
            return torch.empty(0, dtype=torch.float32)

        usable = len(pcm_bytes) - (len(pcm_bytes) % 2)
        values = struct.unpack("<" + "h" * (usable // 2), pcm_bytes[:usable])
        tensor = torch.tensor(values, dtype=torch.float32)
        if channels > 1:
            frame_count = tensor.numel() // channels
            tensor = tensor[: frame_count * channels].reshape(frame_count, channels).mean(dim=1)
        return tensor / 32768.0


class SileroVoiceActivityDetector(VoiceActivitySource):
    """Placeholder for future Silero-VAD integration."""

    def __init__(self, model_path: str, threshold: float = 0.5):
        self.model_path = model_path
        self.threshold = threshold

    def is_speech(self, pcm_frame: bytes, sample_rate: int = 16000) -> bool:
        raise NotImplementedError("Silero-VAD is not implemented yet.")


class VoiceActivityDetector(SileroVoiceActivityDetector):
    """Backward-compatible wrapper for the old VAD class name."""

    def __init__(self, model_path: str, threshold: float = 0.5):
        super().__init__(model_path=model_path, threshold=threshold)
