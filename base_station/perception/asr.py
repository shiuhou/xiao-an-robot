"""ASR interface placeholders.

Future real ASR will use Alibaba SenseVoice-Small. This module only defines
interfaces and fake sources for local tests; it does not load real models.
"""

from __future__ import annotations


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
