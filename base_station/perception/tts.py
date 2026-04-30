"""
tts.py - Text-to-Speech synthesis using edge-tts
Author: 郑斯悦
"""


class TTSEngine:
    def __init__(self, output_dir: str, voice: str = "zh-CN-XiaoxiaoNeural"):
        # TODO: configure edge-tts output directory and voice
        self.output_dir = output_dir
        self.voice = voice

    async def synthesize(self, text: str, audio_id: str) -> tuple[str, int]:
        # TODO: synthesize text via edge-tts, return (file_path, duration_ms)
        raise NotImplementedError
