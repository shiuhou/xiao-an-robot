"""
calendar.py - Skill: query and announce upcoming calendar events
Author: 张子尧
"""


class CalendarSkill:
    name = "calendar"

    def __init__(self, gateway):
        # TODO: store gateway ref, configure calendar source (e.g. CalDAV or local ICS)
        self.gateway = gateway

    async def run(self, trigger: dict):
        # TODO: fetch upcoming events, build TTS summary, send to robot
        raise NotImplementedError
