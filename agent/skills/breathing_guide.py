"""
breathing_guide.py - Skill: guide user through breathing exercise
Author: 张子尧
"""


class BreathingGuideSkill:
    name = "breathing_guide"

    def __init__(self, gateway):
        # TODO: store gateway ref
        self.gateway = gateway

    async def run(self, trigger: dict):
        # TODO: send timed TTS cues (inhale/hold/exhale) + expression + motion sequence
        raise NotImplementedError
