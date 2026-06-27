"""ASR interface placeholders.

Future real ASR will use Alibaba SenseVoice-Small. This module only defines
interfaces and fake sources for local tests; it does not load real models.
"""

from __future__ import annotations

from pathlib import Path


PATTERN_TRANSCRIPTS = {
    "tired": "我有点累",
    "negative": "我今天好烦",
    "normal": "帮我查一下天气",
    "openclaw": "帮我查一下天气",
    "greeting": "你好小安",
    "summary": "生成今天总结",
    "work": "我刚刚在写项目代码",
}


class ASRTranscriptSource:
    """Base interface for ASR transcript sources."""

    def read_transcript(self) -> str | None:
        raise NotImplementedError("ASR transcript reading is not implemented.")


class FakeASRTranscriptSource(ASRTranscriptSource):
    """Return pre-defined transcripts one by one."""

    def __init__(self, transcripts: list[str | None]):
        self.transcripts = list(transcripts)
        self._index = 0

    def read_transcript(self) -> str | None:
        if self._index >= len(self.transcripts):
            return None
        transcript = self.transcripts[self._index]
        self._index += 1
        return transcript


class FakeASRBackend:
    """Mock ASR backend for file-first software tests."""

    def __init__(self, transcript: str | None = None, pattern: str | None = None):
        self.transcript = transcript
        self.pattern = pattern or "normal"

    def transcribe(self, audio_clip: dict) -> dict:
        text = self.transcript
        if text is None:
            try:
                text = PATTERN_TRANSCRIPTS[self.pattern]
            except KeyError as exc:
                supported = ", ".join(sorted(PATTERN_TRANSCRIPTS))
                raise ValueError(f"Unsupported ASR pattern: {self.pattern}. Supported patterns: {supported}.") from exc
        return {
            "text": text,
            "language": "zh",
            "confidence": 0.9 if text else 0.0,
            "backend": "fake",
            "duration_ms": int(audio_clip.get("duration_ms") or 0),
        }


class SenseVoiceASRBackend:
    """SenseVoice ASR shell; never downloads models automatically."""

    def __init__(self, model_dir: str | None = None, device: str = "cpu"):
        self.model_dir = model_dir
        self.device = device

    def transcribe(self, audio_clip: dict) -> dict:
        if not self.model_dir:
            raise RuntimeError("SenseVoice ASR requires a local --asr-model-path; automatic download is disabled.")
        path = Path(self.model_dir).expanduser()
        if not path.exists():
            raise FileNotFoundError(f"SenseVoice ASR model directory does not exist: {self.model_dir}")
        try:
            __import__("funasr")
        except ImportError as exc:
            raise ImportError("SenseVoice ASR requires funasr installed in the project .venv.") from exc
        raise RuntimeError("SenseVoice ASR backend shell is present, but real inference is not wired in Step 42.")


class SenseVoiceSmallASRTranscriptSource(ASRTranscriptSource):
    """Placeholder for future SenseVoice-Small ASR integration."""

    def __init__(self, model_dir: str, device: str = "cpu"):
        self.model_dir = model_dir
        self.device = device

    def read_transcript(self) -> str | None:
        raise NotImplementedError("SenseVoice-Small ASR is not implemented yet.")

    def transcribe_audio(self, audio_path: str) -> str:
        raise NotImplementedError("SenseVoice-Small ASR is not implemented yet.")

    def transcribe_pcm(self, pcm_chunk: bytes, sample_rate: int = 16000) -> str:
        raise NotImplementedError("SenseVoice-Small ASR is not implemented yet.")

    def reset(self) -> None:
        return None


class StreamingASR(SenseVoiceSmallASRTranscriptSource):
    """Backward-compatible wrapper for the old streaming ASR class name."""

    def __init__(self, model_dir: str, device: str = "cpu"):
        super().__init__(model_dir=model_dir, device=device)

    def feed_audio(self, pcm_chunk: bytes) -> str | None:
        raise NotImplementedError("SenseVoice-Small streaming ASR is not implemented yet.")
