"""
asr.py - Automatic Speech Recognition using Sherpa-ONNX (streaming)
Author: 郑斯悦
"""


class StreamingASR:
    def __init__(self, model_dir: str):
        # TODO: initialize sherpa-onnx streaming recognizer
        self.model_dir = model_dir

    def feed_audio(self, pcm_chunk: bytes) -> str | None:
        # TODO: feed chunk, return partial/final transcript or None
        raise NotImplementedError

    def reset(self):
        # TODO: reset decoder state between utterances
        raise NotImplementedError
