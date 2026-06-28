"""ASR interfaces and file-first backends."""

from __future__ import annotations

from pathlib import Path
import re
import time


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
    """Local SenseVoice ASR backend backed by FunASR.

    The model is loaded lazily on first transcription and is never downloaded
    by this class. Callers must provide a populated local model directory.
    """

    def __init__(self, model_dir: str | None = None, device: str = "cpu"):
        self.model_dir = model_dir
        self.device = device
        self._model = None

    def transcribe(self, audio_clip: dict) -> dict:
        started = time.monotonic()
        model_dir = self._validate_model_dir()
        model = self._load_model(model_dir)
        audio_path = audio_clip.get("audio_path")
        if not audio_path:
            raise RuntimeError("SenseVoice ASR requires audio_clip['audio_path'] for file transcription.")

        result = model.generate(input=str(audio_path))
        text, language, confidence = self._parse_result(result)
        duration_ms = int((time.monotonic() - started) * 1000)
        return {
            "text": text,
            "language": language,
            "confidence": confidence,
            "backend": "sensevoice",
            "duration_ms": duration_ms,
            "model_dir": str(model_dir),
            "device": self.device,
        }

    def _validate_model_dir(self) -> Path:
        if not self.model_dir:
            raise RuntimeError("SenseVoice ASR requires a local --asr-model-path; automatic download is disabled.")
        path = Path(self.model_dir).expanduser()
        if not path.exists():
            raise FileNotFoundError(f"SenseVoice ASR model directory does not exist: {self.model_dir}")
        if not path.is_dir():
            raise RuntimeError(f"SenseVoice ASR model path is not a directory: {self.model_dir}")
        if not any(path.iterdir()):
            raise RuntimeError(f"SenseVoice ASR model directory is empty: {self.model_dir}")
        return path

    def _load_model(self, model_dir: Path):
        if self._model is not None:
            return self._model
        try:
            from funasr import AutoModel
        except ImportError as exc:
            raise ImportError("SenseVoice ASR requires funasr installed in the project .venv.") from exc

        self._model = AutoModel(
            model=str(model_dir),
            trust_remote_code=True,
            device=self.device,
            disable_update=True,
        )
        return self._model

    @classmethod
    def _parse_result(cls, result) -> tuple[str, str | None, float | None]:
        item = result
        if isinstance(result, list):
            item = result[0] if result else {}

        language = None
        confidence = None
        if isinstance(item, dict):
            raw_text = item.get("text") or item.get("sentence") or item.get("transcript") or ""
            language = item.get("language") or item.get("lang")
            confidence = item.get("confidence") or item.get("score")
        else:
            raw_text = item

        text = str(raw_text or "").strip()
        text, detected_language = cls._clean_sensevoice_text(text)
        return text, language or detected_language, confidence

    @staticmethod
    def _clean_sensevoice_text(text: str) -> tuple[str, str | None]:
        detected_language = None
        for tag in re.findall(r"<\|([^|]+)\|>", text):
            if tag in {"zh", "en", "yue", "ja", "ko"}:
                detected_language = tag
                break
        text = re.sub(r"<\|[^|]+\|>", "", text).strip()
        return text, detected_language


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
