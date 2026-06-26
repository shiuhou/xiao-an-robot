"""
Deprecated screen report placeholder.

Screen monitoring exited the MVP in Step 30.1. Keep this skill only for legacy
imports until a later cleanup.
"""


class ScreenReportSkill:
    name = "screen_report"

    def __init__(self, gateway, memory):
        # TODO: store gateway and memory refs
        self.gateway = gateway
        self.memory = memory

    async def run(self, trigger: dict):
        # TODO: query screen_usage table, detect overuse, generate TTS nudge
        raise NotImplementedError
