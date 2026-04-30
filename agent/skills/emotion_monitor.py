"""
emotion_monitor.py - Skill: react to sustained emotional states
Author: 张子尧
"""


class EmotionMonitorSkill:
    name = "emotion_monitor"

    def __init__(self, gateway, memory):
        # TODO: store gateway and memory refs
        self.gateway = gateway
        self.memory = memory

    async def run(self, trigger: dict):
        # TODO: check emotion thresholds from trigger, decide response (expression + TTS)
        raise NotImplementedError
