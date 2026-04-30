"""
stream_handler.py - Audio/video stream processing pipeline
Author: 郑斯悦
"""


class StreamHandler:
    def __init__(self, config: dict):
        # TODO: initialize VAD, ASR, face emotion, head pose pipelines
        self.config = config

    async def handle_audio_frame(self, pcm_frame: bytes):
        # TODO: VAD -> ASR -> audio_emotion pipeline
        raise NotImplementedError

    async def handle_video_frame(self, jpeg_data: bytes, timestamp: int):
        # TODO: face_emotion -> head_pose pipeline
        raise NotImplementedError
