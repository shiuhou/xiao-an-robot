"""
brain.py - Main agent orchestrator for Xiao An
Author: 张子尧
"""


class Brain:
    def __init__(self, config_path: str = "config.yaml"):
        # TODO: initialize memory, context_builder, llm_client, gateway, skills
        self.config_path = config_path

    def run(self):
        # TODO: start event loop, listen for triggers from base_station
        raise NotImplementedError

    async def handle_trigger(self, trigger: dict):
        # TODO: build context, call LLM, execute skill, send response to robot
        raise NotImplementedError
