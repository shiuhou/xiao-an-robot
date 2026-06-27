"""Voice activity detection interface placeholders.

Future real VAD will use Silero-VAD. This module only defines interfaces and
fake detectors for local tests; it does not load real models.
"""

from __future__ import annotations

from pathlib import Path
import struct


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
    """Silero VAD shell; never downloads models automatically."""

    def __init__(self, model_path: str | None = None, threshold: float = 0.5):
        self.model_path = model_path
        self.threshold = threshold

    def analyze(self, audio_clip: dict) -> dict:
        if not self.model_path:
            raise RuntimeError("Silero VAD requires a local --vad-model-path; automatic download is disabled.")
        path = Path(self.model_path).expanduser()
        if not path.exists():
            raise FileNotFoundError(f"Silero VAD model file does not exist: {self.model_path}")
        try:
            __import__("torch")
        except ImportError as exc:
            raise ImportError("Silero VAD requires torch installed in the project .venv.") from exc
        raise RuntimeError("Silero VAD backend shell is present, but real inference is not wired in Step 42.")


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
