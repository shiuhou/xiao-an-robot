"""
gateway.py - WebSocket client connecting agent to base station
Author: 张子尧
"""


class Gateway:
    def __init__(self, host: str, port: int):
        # TODO: initialize WebSocket client to base station
        self.host = host
        self.port = port

    async def connect(self):
        # TODO: establish WS connection
        raise NotImplementedError

    async def send_expression(self, expression: str, duration_ms: int = 0):
        # TODO: send display.expression command via base station -> robot
        raise NotImplementedError

    async def send_motion(self, action: str, params: dict = None):
        # TODO: send motion.execute command
        raise NotImplementedError

    async def send_tts(self, text: str):
        # TODO: synthesize TTS and send audio.play_tts command
        raise NotImplementedError
