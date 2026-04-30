"""
morning_brief.py - Skill: deliver morning briefing (weather, schedule, habits)
Author: 张子尧
"""


class MorningBriefSkill:
    name = "morning_brief"

    def __init__(self, gateway, memory):
        # TODO: store gateway and memory refs
        self.gateway = gateway
        self.memory = memory

    async def run(self, trigger: dict):
        # TODO: fetch weather, today's calendar events, pending habits; send TTS brief
        raise NotImplementedError
