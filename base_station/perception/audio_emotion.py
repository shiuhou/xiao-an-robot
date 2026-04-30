"""
audio_emotion.py - Audio-based emotion detection
Author: 郑斯悦
"""


class AudioEmotionDetector:
    EMOTIONS = ['neutral', 'happy', 'sad', 'angry', 'fearful']

    def __init__(self, model_path: str, device: str = "CPU"):
        # TODO: load audio emotion model
        self.model_path = model_path
        self.device = device

    def detect(self, pcm_buffer: bytes) -> dict:
        # TODO: run inference, return {'emotion': str, 'confidence': float}
        raise NotImplementedError
