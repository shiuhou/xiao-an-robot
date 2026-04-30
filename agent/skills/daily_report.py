"""
daily_report.py - Skill: generate and deliver end-of-day emotional summary
Author: 张子尧
"""


class DailyReportSkill:
    name = "daily_report"

    def __init__(self, gateway, memory):
        # TODO: store gateway and memory refs
        self.gateway = gateway
        self.memory = memory

    async def run(self, trigger: dict):
        # TODO: aggregate day's emotion data, build LLM summary, send TTS to robot
        raise NotImplementedError
