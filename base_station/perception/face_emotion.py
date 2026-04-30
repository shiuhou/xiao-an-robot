"""
face_emotion.py - Intel NPU face emotion detection using OpenVINO
Author: 郑斯悦
"""


class FaceEmotionDetector:
    EMOTIONS = ['neutral', 'happy', 'sad', 'surprised', 'angry', 'disgusted', 'fearful']

    def __init__(self, model_path: str, device: str = "NPU"):
        # TODO: load OpenVINO model
        self.model_path = model_path
        self.device = device

    def detect(self, frame) -> dict:
        # TODO: run inference, return emotion + confidence + fatigue_score
        raise NotImplementedError
