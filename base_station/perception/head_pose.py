"""
head_pose.py - Intel NPU head pose estimation using OpenVINO
Author: 郑斯悦
"""


class HeadPoseEstimator:
    def __init__(self, model_path: str, device: str = "NPU"):
        # TODO: load OpenVINO model
        self.model_path = model_path
        self.device = device

    def estimate(self, frame) -> dict:
        # TODO: run inference, return {'yaw': float, 'pitch': float, 'roll': float}
        raise NotImplementedError
