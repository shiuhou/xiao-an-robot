"""
habit_tracker.py - Skill: track habits and send reminder/encouragement
Author: 张子尧
"""


class HabitTrackerSkill:
    name = "habit_tracker"

    def __init__(self, gateway, memory):
        # TODO: store gateway and memory refs
        self.gateway = gateway
        self.memory = memory

    async def run(self, trigger: dict):
        # TODO: check overdue habits, send TTS reminder with streak info
        raise NotImplementedError

    async def mark_done(self, habit_name: str):
        # TODO: update current_streak and last_done in habits table
        raise NotImplementedError
