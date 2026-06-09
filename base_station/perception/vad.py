"""Voice activity detection interface placeholders.

Future real VAD will use Silero-VAD. This module only defines interfaces and
fake detectors for local tests; it does not load real models.
"""

from __future__ import annotations


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
