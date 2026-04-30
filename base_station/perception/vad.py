"""
vad.py - Voice Activity Detection using Silero VAD
Author: 郑斯悦
"""


class VoiceActivityDetector:
    def __init__(self, model_path: str):
        # TODO: load Silero VAD ONNX model
        self.model_path = model_path

    def is_speech(self, pcm_frame: bytes) -> bool:
        # TODO: run VAD inference, return True if speech detected
        raise NotImplementedError
